"""Run with: python -m psnself.web"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("psnself.web.app:app", host="0.0.0.0", port=8420, reload=False)