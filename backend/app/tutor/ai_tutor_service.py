from typing import List, Dict, Optional
import google.generativeai as genai
from app.core.config import settings
from app.core.models import (
    Topology, DiagnosticReport, TutorChatRequest, TutorChatResponse, DiagnosticFinding
)
from app.tutor.prompt_templates import SYSTEM_SOCRATIC_TUTOR_PROMPT, build_tutor_user_prompt

class AITutorService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.has_gemini = bool(self.api_key and len(self.api_key.strip()) > 10)
        if self.has_gemini:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(
                    model_name="gemini-1.5-flash",
                    system_instruction=SYSTEM_SOCRATIC_TUTOR_PROMPT
                )
            except Exception as e:
                print(f"[AITutorService] Advertencia configurando Gemini: {e}")
                self.has_gemini = False

    def generate_response(
        self,
        request: TutorChatRequest,
        topology: Topology,
        report: DiagnosticReport
    ) -> TutorChatResponse:
        hint_level = request.hint_level or 1

        # Si el usuario seleccionó un hallazgo específico
        selected_finding: Optional[DiagnosticFinding] = None
        if request.selected_finding_id:
            selected_finding = next(
                (f for f in report.findings if f.id == request.selected_finding_id), None
            )

        # Si no hay clave de Gemini o falla la llamada, usar tutor heurístico determinista
        if not self.has_gemini:
            return self._generate_heuristic_response(request, selected_finding, report, hint_level)

        # Usar Gemini con contexto enriquecido
        try:
            topo_summary = self._summarize_topology(topology)
            findings_summary = self._summarize_findings(report, selected_finding)
            prompt = build_tutor_user_prompt(
                user_message=request.user_message,
                topology_summary=topo_summary,
                findings_summary=findings_summary,
                hint_level=hint_level
            )
            response = self.model.generate_content(prompt)
            reply_text = response.text

            highlight_devs = [selected_finding.device_id] if selected_finding else [f.device_id for f in report.findings[:2]]
            highlight_ifs = [selected_finding.interface_name] if selected_finding and selected_finding.interface_name else []

            return TutorChatResponse(
                tutor_reply=reply_text,
                hint_level_provided=hint_level,
                recommended_next_action="Aplica la pista y vuelve a analizar la práctica.",
                highlight_devices=highlight_devs,
                highlight_interfaces=highlight_ifs
            )
        except Exception as e:
            print(f"[AITutorService] Error al llamar a Gemini: {e}")
            return self._generate_heuristic_response(request, selected_finding, report, hint_level)

    def _generate_heuristic_response(
        self,
        request: TutorChatRequest,
        finding: Optional[DiagnosticFinding],
        report: DiagnosticReport,
        hint_level: int
    ) -> TutorChatResponse:
        """
        Respuesta pedagógica estructurada sin requerir llamadas externas a API.
        """
        if not finding and report.findings:
            # Tomar el primer hallazgo crítico
            finding = report.findings[0]

        if not finding:
            return TutorChatResponse(
                tutor_reply="🎉 **¡Excelente trabajo!** No he detectado problemas evidentes en la topología analizada. Todos los enlaces y configuraciones clave parecen coherentes.",
                hint_level_provided=hint_level,
                recommended_next_action="Verifica la conectividad extremo a extremo con pings de prueba."
            )

        highlight_devs = [finding.device_id]
        if finding.related_device_id:
            highlight_devs.append(finding.related_device_id)

        highlight_ifs = [finding.interface_name] if finding.interface_name else []

        if hint_level == 1:
            reply = (
                f"⚠️ **Observación en {finding.device_name}**: {finding.title}\n\n"
                f"💡 **Pista conceptual (Nivel 1)**:\n{finding.hint_level1}\n\n"
                f"*¿Te gustaría que te indique qué interfaz o equipo revisar (Pista Nivel 2) o prefieres analizarlo primero?*"
            )
            action = "Reflexiona sobre la pregunta y revisa los conceptos teóricos."
        elif hint_level == 2:
            reply = (
                f"🔍 **Pista de Componente (Nivel 2)**:\n"
                f"{finding.hint_level2}\n\n"
                f"📌 **Detalle del problema:**\n{finding.description}\n\n"
                f"*Si necesitas la solución detallada y los comandos IOS exactos, solicita el Nivel 3.*"
            )
            action = f"Inspecciona la configuración en {finding.device_name}."
        else: # Nivel 3
            reply = (
                f"🛠️ **Diagnóstico Técnico y Solución (Nivel 3)**:\n\n"
                f"**Problema:** {finding.description}\n\n"
                f"**Solución recomendada:**\n```cisco\n{finding.technical_solution}\n```"
            )
            action = "Aplica los comandos en Packet Tracer y presiona 'Re-analizar Red'."

        return TutorChatResponse(
            tutor_reply=reply,
            hint_level_provided=hint_level,
            recommended_next_action=action,
            highlight_devices=highlight_devs,
            highlight_interfaces=highlight_ifs
        )

    def _summarize_topology(self, topology: Topology) -> str:
        devs = [f"- {d.name} ({d.type.value}): {len(d.interfaces)} interfaces" for d in topology.devices]
        links = [f"- {l.source_device}:{l.source_interface} <--> {l.target_device}:{l.target_interface}" for l in topology.links]
        return f"Dispositivos:\n" + "\n".join(devs) + f"\n\nEnlaces:\n" + "\n".join(links)

    def _summarize_findings(self, report: DiagnosticReport, selected: Optional[DiagnosticFinding]) -> str:
        if selected:
            return f"Hallazgo enfocado: {selected.title} en {selected.device_name} ({selected.description})"
        lines = [f"- [{f.severity.value.upper()}] {f.device_name} ({f.interface_name or 'global'}): {f.title} -> {f.description}" for f in report.findings]
        return "\n".join(lines)

ai_tutor_service = AITutorService()
