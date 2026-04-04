from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app = FastAPI()

# Serve static files for PWA
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
async def read_index():
    return FileResponse('frontend/index.html')

@app.get("/landing")
async def read_landing():
    return FileResponse('frontend/landing.html')

@app.get("/manifest.json")
async def read_manifest():
    return FileResponse('frontend/manifest.json')

@app.get("/sw.js")
async def read_sw():
    return FileResponse('frontend/sw.js')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
