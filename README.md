# RadvanSec — Django project

A minimal Django project that reproduces the current static site (home page) and
replaces the hand-written blog HTML with a real `Post` model + admin panel.

```
radvansec/        project settings, root urls, home view
blog/             blog app: model, admin, views, urls, fixture with the first post
templates/        home.html, blog/list.html, blog/detail.html
static/           css/site.css (home page), css/blog.css (blog pages), img/logo.png
```

## 1. Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then edit values, see below
export $(cat .env | xargs)         # or use a tool like django-environ/python-dotenv

python manage.py migrate
python manage.py loaddata blog/fixtures/initial_posts.json   # seeds the first post
python manage.py createsuperuser   # your admin login
```

## 2. Run it

```bash
python manage.py runserver 0.0.0.0:8001
```

Visit:
- `http://127.0.0.1:8001/` — home page
- `http://127.0.0.1:8001/blog/` — blog list
- `http://127.0.0.1:8001/<DJANGO_ADMIN_PATH>` — admin panel (default `admin/`, see `.env.example`)

Writing a new post from now on: log into the admin, add a `Post`. Title, summary,
read time, published date, and the body as HTML (headings `<h2>`, paragraphs `<p>`,
code blocks `<pre><code>...</code></pre>`, lists, and `<div class="callout">...</div>`
for the highlighted tip box — the same classes already used by the existing post,
styled in `static/css/blog.css`). Leave slug blank to auto-generate it from the title.

## 3. Environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Random secret, required in production. Generate one with `python -c "import secrets;print(secrets.token_urlsafe(50))"` |
| `DJANGO_DEBUG` | `True` locally, `False` in production |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated: `radvansec.com,www.radvansec.com` |
| `DJANGO_ADMIN_PATH` | Change from `admin/` to something non-guessable in production, e.g. `panel-x7k/` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated full origins, e.g. `https://radvansec.com` |

## 4. Production deployment (port 8001, behind Nginx)

On the server:

```bash
cd /path/to/radvansec_django
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values, DJANGO_DEBUG=False

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

Run with Gunicorn instead of the dev server:

```bash
gunicorn radvansec.wsgi:application --bind 127.0.0.1:8001 --workers 3
```

For it to survive reboots/crashes, run it as a systemd service, e.g.
`/etc/systemd/system/radvansec.service`:

```ini
[Unit]
Description=RadvanSec Django app
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/radvansec_django
EnvironmentFile=/path/to/radvansec_django/.env
ExecStart=/path/to/radvansec_django/.venv/bin/gunicorn radvansec.wsgi:application --bind 127.0.0.1:8001 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now radvansec
```

Then point Nginx at it and let Nginx serve `/static/` and `/media/` directly:

```nginx
server {
    listen 80;
    server_name radvansec.com www.radvansec.com;

    location /static/ {
        alias /path/to/radvansec_django/staticfiles/;
    }
    location /media/ {
        alias /path/to/radvansec_django/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Put HTTPS (certbot/Let's Encrypt) in front of this as usual; the security settings in
`settings.py` (HSTS, secure cookies, SSL redirect) activate automatically once
`DJANGO_DEBUG=False`.

## 5. Notes

- `Post.body_html` is rendered unescaped (`{{ post.body_html|safe }}`). Only paste
  HTML you wrote or trust, since it is not sanitized, by design, so it can contain
  code blocks with raw `<`/`>`.
- The admin path, secret key, and allowed hosts all come from environment variables,
  never hardcode them when you deploy.
- Change the default admin path (`DJANGO_ADMIN_PATH`) before going live.
