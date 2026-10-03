from fastapi import APIRouter
from app.core.models import DiagnosticReport
from app.engine.rule_engine import rule_engine
from app.api.routes_topology import current_topology

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])

@router.get("/run", response_model=DiagnosticReport)
@router.post("/run", response_model=DiagnosticReport)
def run_diagnostics():
    """
    Ejecuta el motor de reglas determinista de NetTutorIA sobre la topología
    actual y entrega el informe de inconsistencias y fallas encontradas.
    """
    report = rule_engine.analyze(current_topology)
    return report
