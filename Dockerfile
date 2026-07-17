FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir .[web]

EXPOSE 8420

VOLUME ["/root/.config/psnself"]

CMD ["python", "-m", "psnself.web"]
