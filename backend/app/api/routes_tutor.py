from fastapi import APIRouter
from app.core.models import TutorChatRequest, TutorChatResponse
from app.tutor.ai_tutor_service import ai_tutor_service
from app.engine.rule_engine import rule_engine
from app.api.routes_topology import current_topology

router = APIRouter(prefix="/tutor", tags=["Tutor"])

@router.post("/chat", response_model=TutorChatResponse)
def tutor_chat(request: TutorChatRequest):
    """
    Conversa con NetTutor para obtener retroalimentación pedagógica,
    pistas adaptativas por niveles (1: conceptual, 2: componente, 3: solución)
    o resolver dudas del estudiante sobre su práctica.
    """
    # Ejecutar diagnóstico fresco sobre la topología actual
    report = rule_engine.analyze(current_topology)
    response = ai_tutor_service.generate_response(request, current_topology, report)
    return response
