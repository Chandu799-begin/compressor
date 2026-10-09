# SmartCompress Pro

> **Compress Smarter. Share Faster.**
>
> A premium, production-ready Django web application that compresses images and
> documents to an exact target size in **KB, MB or GB** — with a modern animated
> glassmorphism UI, REST API, authentication, background jobs and secure downloads.

---

## Table of contents

1. [Features](#features)
2. [Tech stack](#tech-stack)
3. [Project structure](#project-structure)
4. [Quick start (Windows + VS Code)](#quick-start-windows--vs-code)
5. [Environment variables](#environment-variables)
6. [Running Celery + Redis (optional)](#running-celery--redis-optional)
7. [Ghostscript (optional PDF compression)](#ghostscript-optional-pdf-compression)
8. [LibreOffice (document format conversion)](#libreoffice-document-format-conversion)
9. [Format conversion](#format-conversion)
10. [How compression works](#how-compression-works)
11. [REST API](#rest-api)
12. [Testing](#testing)
13. [Deployment](#deployment)

---

## Features

- **Image compression** — JPG, JPEG, PNG, WEBP (plus BMP/GIF/TIFF input).
  Iterative quality search + optional resolution reduction hits the target size.
  Resize, keep aspect ratio, strip EXIF metadata, transparency safe.
- **Format conversion** — change the output format of images (JPG/PNG/WEBP) and
  documents (PDF/DOCX/XLSX/PPTX) while compressing. Image conversion is native
  (Pillow); document conversion uses LibreOffice when installed.
- **Document compression** — PDF (PyMuPDF, optional Ghostscript), DOCX, XLSX, PPTX.
  Embedded media is re-encoded while paragraphs, tables, formulas and slides stay intact.
- **Target sizes** — presets in KB/MB/GB plus a custom value with unit dropdown.
  Binary conversions (1 KB = 1,024 B, 1 MB = 1,048,576 B, 1 GB = 1,073,741,824 B).
  Output is compressed to the target or as close as possible without exceeding it;
  files already under target are never enlarged.
- **Honest results** — if a target cannot be reached safely, a clear warning is returned.
- **Premium UI** — deep navy/blue/purple/cyan gradients, glassmorphism, 3D floating
  file icons, GSAP animations, dark & light mode, toasts, skeleton/progress states.
- **Uploads** — animated drag & drop, multi-file, validation, and chunked uploads
  for GB-sized files (streamed to disk, never fully loaded into memory).
- **Auth** — register, login/logout, password reset, profile, personal dashboard,
  compression history, delete history, secure file serving.
- **API** — Django REST Framework endpoints with throttling and pagination.
- **Background jobs** — Celery tasks with an inline (eager) development mode.
- **Security** — extension + MIME + magic-number validation, CSRF, rate limiting,
  upload/resource limits, protected downloads by owner/session.

---

## Tech stack

| Layer            | Technology                                                        |
| ---------------- | ----------------------------------------------------------------- |
| Backend          | Python 3.13, Django 5.x, Django ORM, SQLite                       |
| API              | Django REST Framework                                             |
| Background       | Celery + Redis (optional; eager mode by default)                  |
| Images           | Pillow                                                            |
| PDF              | PyMuPDF + optional Ghostscript                                    |
| Office           | python-docx, openpyxl, python-pptx, `zipfile`                     |
| Frontend         | HTML5, CSS3, ES6, Bootstrap 5, Font Awesome, Google Fonts, GSAP   |

---

## Project structure

```
compressor/                     # repository root
├── manage.py
├── requirements.txt
├── .env.example
├── smartcompress_pro/          # Django project package
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   ├── asgi.py
│   └── celery.py
├── compressor/                 # main app
│   ├── models.py               # UploadedFile, CompressionJob, CompressedFile
│   ├── views.py                # pages + AJAX API
│   ├── api.py                  # DRF viewsets
│   ├── serializers.py
│   ├── forms.py
│   ├── tasks.py                # Celery tasks
│   ├── validators.py
│   ├── urls.py
│   ├── admin.py
│   ├── tests.py
│   └── services/
│       ├── size_converter.py
│       ├── image_compressor.py
│       ├── pdf_compressor.py
│       ├── office_compressor.py
│       ├── converter.py
│       └── dispatcher.py
├── accounts/                   # auth app (Profile, register, profile, reset)
├── templates/                  # base, home, compressor, dashboard, auth, ...
├── static/
│   ├── css/  (premium.css, animations.css, responsive.css)
│   └── js/   (dashboard.js, upload.js, compressor.js)
└── media/                      # uploads/ compressed/ avatars/
```

---

## Quick start (Windows + VS Code)

Open **PowerShell** in the project folder (`C:\Django_jan23_4pm\compressor`).

```powershell
# 1. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# If script execution is blocked, run once:
# Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 2. Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 3. Create your environment file
Copy-Item .env.example .env

# 4. Apply database migrations
python manage.py migrate

# 5. Create an admin account (optional)
python manage.py createsuperuser

# 6. Run the development server
python manage.py runserver
```

Then open <http://127.0.0.1:8000/>.

> **Important:** always run commands with the virtual environment activated
> (`.\venv\Scripts\Activate.ps1`) so the project dependencies — not the global
> Python — are used.

### macOS / Linux equivalent

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

---

## Environment variables

All settings are read from `.env` (see `.env.example`). Highlights:

| Variable              | Default                     | Purpose                             |
| --------------------- | --------------------------- | ----------------------------------- |
| `DJANGO_SECRET_KEY`   | dev key                     | Set a long random value in prod     |
| `DJANGO_DEBUG`        | `True`                      | Turn off in production              |
| `DJANGO_ALLOWED_HOSTS`| `127.0.0.1,localhost`       | Comma separated hosts               |
| `MAX_UPLOAD_SIZE`     | `4294967296` (4 GB)         | Absolute upload ceiling             |
| `CELERY_EAGER`        | `True`                      | Run tasks inline (no broker needed) |
| `CELERY_BROKER_URL`   | `redis://127.0.0.1:6379/0`  | Redis broker for Celery             |
| `GHOSTSCRIPT_BINARY`  | *(empty)*                   | Path to `gswin64c`/`gs` (optional)  |
| `LIBREOFFICE_BINARY`  | *(empty)*                   | Path to `soffice` for conversions   |

---

## Running Celery + Redis (optional)

In development the project runs compression **inline** (`CELERY_EAGER=True`), so no
broker is required. For large files set `CELERY_EAGER=False` and start Redis plus a
worker:

```powershell
# Requires a running Redis server on 127.0.0.1:6379
celery -A smartcompress_pro worker -l info
# Optional periodic cleanup (beat):
celery -A smartcompress_pro beat -l info
```

The `compressor.cleanup_temp_files` task deletes old jobs and orphaned files.

---

## Ghostscript (optional PDF compression)

Install Ghostscript from <https://www.ghostscript.com/> and either add `gswin64c`
to your `PATH` or set `GHOSTSCRIPT_BINARY` in `.env`. When present it is used for
strong "ebook/screen" downsampling; otherwise PyMuPDF is used.

---

## LibreOffice (document format conversion)

Converting between document formats (for example DOCX → PDF, or PDF → DOCX) is
performed by [LibreOffice](https://www.libreoffice.org/) in headless mode.
Install it and either add `soffice` to your `PATH` or set `LIBREOFFICE_BINARY` in
`.env`:

```powershell
# Example Windows path
LIBREOFFICE_BINARY=C:\Program Files\LibreOffice\program\soffice.exe
```

If LibreOffice is not available, format conversion of documents is skipped with a
clear note and the file is still compressed in its original format. Image format
conversion needs no extra software.

---

## Format conversion

Pick **Keep original format** (default) or select a target format in the
compressor's *Output format* control:

| Files            | Available output formats                |
| ---------------- | ---------------------------------------- |
| Images           | JPG / JPEG, PNG, WEBP                    |
| PDF / DOCX / XLSX / PPTX | PDF, DOCX, XLSX, PPTX           |

- **Images** are converted natively by Pillow. Transparency is preserved for PNG
  and WEBP; converting a transparent image to JPG flattens it onto white.
- **Documents** are converted with LibreOffice (see above), then compressed. XML
  structure, tables, formulas and slides are preserved by the conversion.
- Requested-size targeting and format conversion can be combined in one job.

---

## How compression works

- **Images** — the engine binary-searches JPEG/WEBP quality under the target, then
  progressively reduces resolution if needed. PNG targets are met via palette
  quantisation and scaling. Output is never larger than the original unless a
  format conversion was requested.
- **Target size** — the result is guaranteed to be **at or under** the requested
  size; the engine keeps the highest quality that still fits, so results land as
  close to the target as the codec allows. Impossible targets return a warning.
- **PDF** — rebuilds the file with `garbage=4` and deflated streams, optionally
  downsampling embedded raster images through a gentle→aggressive ladder.
- **Office** — rebuilds the OOXML ZIP, re-encoding `*/media/*` images at the same
  format (so nothing breaks) and maximising ZIP deflate. All XML parts are copied
  byte-for-byte, preserving layout.

Compression savings are reported as `((original − compressed) / original) × 100`.

---

## REST API

Authentication uses session cookies. All endpoints are under `/api/rest/`.

| Method | Endpoint                          | Description                        |
| ------ | --------------------------------- | --------------------------------- |
| POST   | `/api/rest/uploads/`              | Upload a file (multipart `file`)  |
| GET    | `/api/rest/uploads/`              | List your uploads                 |
| POST   | `/api/rest/jobs/compress/`        | Start compression for uploads     |
| GET    | `/api/rest/jobs/`                 | List your compression jobs        |
| GET    | `/api/rest/jobs/{id}/status/`     | Live job status                   |
| DELETE | `/api/rest/jobs/{id}/`            | Delete a job and its files        |

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/rest/jobs/compress/ \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"upload_ids":[1],"target_value":100,"target_unit":"KB","level":"medium","output_format":"webp"}'
```

---

## Testing

```powershell
python manage.py test compressor accounts
```

The suite covers size conversion, real image/PDF/Office compression, the
upload→compress→download flow, validation, access control and authentication.

---

## Deployment

1. Set production values in `.env`:
   `DJANGO_DEBUG=False`, a strong `DJANGO_SECRET_KEY`, real `DJANGO_ALLOWED_HOSTS`
   and `CSRF_TRUSTED_ORIGINS`, and `CELERY_EAGER=False`.
2. Collect static files (served by WhiteNoise):
   ```powershell
   python manage.py collectstatic --noinput
   ```
3. Apply migrations and run with a WSGI server (Linux/macOS):
   ```bash
   gunicorn smartcompress_pro.wsgi:application --bind 0.0.0.0:8000 --workers 3
   ```
   On Windows use `waitress-serve` or run behind IIS.
4. Run Redis and a Celery worker for background compression.
5. Put a reverse proxy (Nginx/IIS) in front, terminate TLS, and proxy to the app.
   When `DEBUG=False`, HTTPS redirect, HSTS, secure cookies and content-type
   sniffing protection are enabled automatically.

---

## License

Provided as a portfolio-ready reference project. Use and adapt freely.
