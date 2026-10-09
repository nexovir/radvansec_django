"""
Celery tasks for the cve_monitor app.

sync_pocs:   downloads the public dataset https://github.com/nomi-sec/PoC-in-GitHub
             as one zip archive, stores the PoC repositories in the database,
             then discards the archive.
enrich_cves: fills description / CVSS / CWE from NVD (fallback: CVE.org).
"""
import gc
import hashlib
import io
import json
import logging
import os
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timezone as dt_tz

import requests
from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from cve_monitor.models import CVE, CVEExploit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- config
ZIP_URL = "https://codeload.github.com/nomi-sec/PoC-in-GitHub/zip/refs/heads/master"
TIMEOUT = 300
FILE_RE = re.compile(r"^[^/]+/(\d{4})/(CVE-\d{4}-\d+)\.json$", re.IGNORECASE)

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
MITRE_URL = "https://cveawg.mitre.org/api/cve/{}"
NVD_KEY = os.environ.get("NVD_API_KEY", "")
WORKERS = 5 if NVD_KEY else 1


# ---------------------------------------------------------------- helpers
@contextmanager
def task_lock(name: str, ttl: int):
    """Skip the run if the previous one is still active."""
    key = f"lock:{name}"
    if not cache.add(key, "1", timeout=ttl):
        yield False
        return
    try:
        yield True
    finally:
        cache.delete(key)


def sendmessage(msg, colour=None, telegram=False):
    """Logs the message. Sends to Telegram if enabled and configured."""
    logger.info(msg)
    if not telegram:
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": msg},
            timeout=15,
        )
    except requests.RequestException:
        logger.warning("telegram send failed")


class FetchError(Exception):
    pass


class RateLimited(Exception):
    pass


def _dt(value):
    dt = parse_datetime(value) if value else None
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, dt_tz.utc)
    return dt


def _en(items):
    for d in items or []:
        if d.get("lang", "").startswith("en"):
            return d.get("value", "")
    return ""


# ---------------------------------------------------------------- NVD / MITRE
def fetch_nvd(cve_id: str):
    headers = {"apiKey": NVD_KEY} if NVD_KEY else {}
    r = requests.get(NVD_URL, params={"cveId": cve_id}, headers=headers, timeout=30)
    if r.status_code in (403, 429):
        raise RateLimited()
    r.raise_for_status()
    vulns = r.json().get("vulnerabilities") or []
    if not vulns:
        return None

    c = vulns[0]["cve"]
    desc = _en(c.get("descriptions"))
    if not desc:
        return None

    score = sev = None
    metrics = c.get("metrics", {})
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        if metrics.get(key):
            m = metrics[key][0]
            score = m["cvssData"].get("baseScore")
            sev = m["cvssData"].get("baseSeverity") or m.get("baseSeverity")
            break

    cwes = [
        x["value"]
        for w in c.get("weaknesses", [])
        for x in w.get("description", [])
        if x.get("value", "").startswith("CWE-")
    ]
    return {
        "description": desc,
        "severity": (sev or "").upper(),
        "cvss_score": score,
        "cwe": ", ".join(dict.fromkeys(cwes))[:128],
        "published_at": _dt(c.get("published")),
    }


def fetch_mitre(cve_id: str):
    """Fallback for CVEs NVD has not ingested yet (description only)."""
    r = requests.get(MITRE_URL.format(cve_id), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    j = r.json()
    desc = _en(j.get("containers", {}).get("cna", {}).get("descriptions"))
    if not desc:
        return None
    return {
        "description": desc,
        "severity": "",
        "cvss_score": None,
        "cwe": "",
        "published_at": _dt(j.get("cveMetadata", {}).get("datePublished")),
    }


def _fetch_one(cve_id):
    try:
        return fetch_nvd(cve_id) or fetch_mitre(cve_id), None
    except RateLimited:
        return None, "rate"
    except requests.RequestException as e:
        logger.warning("enrich failed for %s: %s", cve_id, e)
        return None, "error"


def _enrich_cves(batch: int = 0):
    batch = batch or (100 if NVD_KEY else 8)
    todo = list(
        CVE.objects.filter(enriched_at__isnull=True, enrich_attempts__lt=5)
        .order_by(F("discovered_at").desc(nulls_last=True), "-year", "-id")[:batch]
    )

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda c: _fetch_one(c.cve_id), todo))

    done = failed = rate = 0
    for cve, (data, err) in zip(todo, results):
        if err == "rate":
            rate += 1
            continue  # don't count against the CVE
        if data:
            for k, v in data.items():
                setattr(cve, k, v)
            cve.enriched_at = timezone.now()
            cve.save(update_fields=[*data.keys(), "enriched_at"])
            done += 1
        else:
            cve.enrich_attempts += 1
            cve.save(update_fields=["enrich_attempts"])
            failed += 1

    left = CVE.objects.filter(enriched_at__isnull=True, enrich_attempts__lt=5).count()
    return f"enriched={done} failed={failed} rate_limited={rate} pending={left}"


@shared_task(time_limit=900, soft_time_limit=840)
def enrich_cves(batch: int = 0):
    """Fill description / CVSS / CWE for CVEs that have none yet (newest first)."""
    with task_lock("enrich_cves", 960) as ok:
        if not ok:
            return "skipped: previous run still active"
        return _enrich_cves(batch)


# ---------------------------------------------------------------- PoC sync
def download_zip() -> zipfile.ZipFile:
    """Download the archive into memory only (nothing is written to disk)."""
    try:
        resp = requests.get(ZIP_URL, timeout=TIMEOUT)
        resp.raise_for_status()
        buffer = io.BytesIO(resp.content)
        resp.close()
    except requests.RequestException as exc:
        raise FetchError(f"zip download failed: {exc}")
    try:
        return zipfile.ZipFile(buffer)
    except zipfile.BadZipFile as exc:
        raise FetchError(f"bad zip file: {exc}")


def parse_repos(raw: bytes) -> list:
    try:
        data = json.loads(raw)
    except ValueError:
        return []

    repos = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not item.get("full_name"):
            continue
        repos.append({
            "full_name": item["full_name"][:255],
            "url": (item.get("html_url") or f"https://github.com/{item['full_name']}")[:512],
            "description": item.get("description") or "",
            "stars": item.get("stargazers_count") or 0,
            "fork": bool(item.get("fork")),
            "pushed_at": item.get("pushed_at"),
        })

    # non-forks first, then most stars
    repos.sort(key=lambda r: (r["fork"], -r["stars"]))
    return repos


def save_cve(cve_id: str, year: int, digest: str, repos: list, mark_new: bool):
    """Store the CVE and its repos. Returns (cve, created)."""
    top = repos[0]
    defaults = {
        "year": year,
        "file_sha": digest,
        "poc_count": len(repos),
        "top_repo_url": top["url"],
        "top_stars": top["stars"],
    }
    with transaction.atomic():
        cve, created = CVE.objects.get_or_create(cve_id=cve_id, defaults={
            **defaults,
            # only runs after the initial import stamp the discovery time
            "discovered_at": timezone.now() if mark_new else None,
        })
        if not created:
            for k, v in defaults.items():
                setattr(cve, k, v)
            cve.save()

        for r in repos:
            CVEExploit.objects.update_or_create(
                cve=cve,
                repo_full_name=r["full_name"],
                defaults={
                    "repo_url": r["url"],
                    "description": r["description"],
                    "stars": r["stars"],
                    "is_fork": r["fork"],
                    "pushed_at": parse_datetime(r["pushed_at"]) if r.get("pushed_at") else None,
                },
            )
        CVEExploit.objects.filter(cve=cve).exclude(
            repo_full_name__in=[r["full_name"] for r in repos]
        ).delete()
    return cve, created


def notify(cve: CVE, repos: list):
    top = repos[0]
    msg = (
        f"\U0001F525 New public PoC\n"
        f"CVE: {cve.cve_id}\n"
        f"Repo: {top['url']}\n"
        f"\u2B50 {top['stars']} | total PoCs: {len(repos)}\n"
        f"{top['description'][:300]}"
    )
    sendmessage(msg, colour="RED", telegram=True)


def _sync_pocs(min_year: int = 0, silent: bool = False):
    try:
        archive = download_zip()
    except FetchError as e:
        sendmessage(f"[PoC] {e}", colour="RED", telegram=False)
        raise

    seen = changed = created_count = failed = 0
    try:
        known = dict(CVE.objects.filter(year__gte=min_year).values_list("cve_id", "file_sha"))

        for name in archive.namelist():
            m = FILE_RE.match(name)
            if not m:
                continue
            year, cve_id = int(m.group(1)), m.group(2).upper()
            if year < min_year:
                continue
            seen += 1

            raw = archive.read(name)
            digest = hashlib.sha1(raw).hexdigest()
            if known.get(cve_id) == digest:
                continue

            repos = parse_repos(raw)
            if not repos:
                continue

            try:
                cve, created = save_cve(cve_id, year, digest, repos, mark_new=not silent)
                changed += 1
                if created:
                    created_count += 1
                    if not silent:
                        notify(cve, repos)
            except Exception as e:
                failed += 1
                logger.exception("PoC sync failed for %s", cve_id)
                sendmessage(f"[PoC] failed on {cve_id}: {e}", colour="RED", telegram=False)
    finally:
        # The data is in the database now: discard the downloaded archive
        archive.close()
        del archive
        gc.collect()

    summary = f"files={seen} changed={changed} new={created_count} failed={failed}"
    sendmessage(f"[PoC] sync done: {summary}", colour="BLUE", telegram=False)

    if created_count:
        enrich_cves.delay()

    return summary


@shared_task(time_limit=3600, soft_time_limit=3300)
def sync_pocs(min_year: int = 0, silent: bool = False):
    """
    Periodic task.

    min_year: skip CVE files older than this year.
              Use min_year=2000 to import everything.
    silent:   store without sending Telegram messages and without stamping
              discovered_at. Use True for the first import, then False.
    """
    with task_lock("sync_pocs", 3660) as ok:
        if not ok:
            return "skipped: previous run still active"
        return _sync_pocs(min_year, silent)