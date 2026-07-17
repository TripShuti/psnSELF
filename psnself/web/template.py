from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from psnself.web.utils import fmt_date

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["fmt_date"] = fmt_date
