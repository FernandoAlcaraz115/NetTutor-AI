import uvicorn
import sys
from pathlib import Path

# Agregar carpeta backend al PYTHONPATH
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

if __name__ == "__main__":
    print("=" * 60)
    print("Iniciando NetTutorIA - Laboratorio Inteligente de Redes")
    print("URL Web:  http://localhost:8000")
    print("API Docs: http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
