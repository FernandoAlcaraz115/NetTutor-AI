import warnings
from typing import List, Dict, Optional

# Silenciar advertencia de descontinuación de la librería legacy
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
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
                model_name = settings.GEMINI_MODEL or "gemini-2.5-flash"
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=SYSTEM_SOCRATIC_TUTOR_PROMPT
                )
                print(f"[AITutorService] Gemini IA activo con modelo '{model_name}'.")
            except Exception as e:
                print(f"[AITutorService] Advertencia configurando Gemini: {e}")
                self.has_gemini = False
        else:
            print("[AITutorService] Sin GEMINI_API_KEY válida: usando modo heurístico offline.")

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
                hint_level=hint_level,
                chat_history=request.chat_history
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
        dev_blocks = []
        for d in topology.devices:
            header = f"- {d.name} ({d.type.value})"
            meta = []
            if d.default_gateway:
                meta.append(f"GW={d.default_gateway}")
            if d.vlans:
                vlans_str = ", ".join(f"{vid}:{vname}" for vid, vname in sorted(d.vlans.items()))
                meta.append(f"VLANs=[{vlans_str}]")
            if d.static_routes:
                routes_str = "; ".join(
                    f"{r.get('network')}/{r.get('mask')}->{r.get('next_hop')}" for r in d.static_routes
                )
                meta.append(f"Rutas=[{routes_str}]")
            if meta:
                header += " | " + " | ".join(meta)

            if_lines = []
            for iface in d.interfaces:
                parts = [iface.name]
                if iface.ip_address and iface.ip_address != "unassigned":
                    parts.append(f"{iface.ip_address}/{iface.subnet_mask or ''}")
                else:
                    parts.append("sin-IP")
                if iface.dhcp_enabled:
                    parts.append("modo=DHCP")
                elif d.type.value in ("pc", "server"):
                    parts.append("modo=Static")
                if iface.encapsulation_dot1q:
                    parts.append(f"dot1Q={iface.encapsulation_dot1q}")
                if iface.switchport_mode.value == "trunk":
                    t_info = f"trunk(native={iface.native_vlan or 1}"
                    if iface.trunk_allowed_vlans:
                        t_info += f",allowed={iface.trunk_allowed_vlans}"
                    t_info += ")"
                    parts.append(t_info)
                elif iface.switchport_mode.value == "access":
                    parts.append(f"access(vlan={iface.access_vlan or 1})")
                parts.append(f"estado={iface.status.value}")
                if_lines.append("    * " + " ".join(parts))

            # Extraer líneas clave de OSPF / DHCP / helper-address del raw_config si existen
            extra_cfg = []
            if d.raw_config:
                for raw_line in d.raw_config.splitlines():
                    s = raw_line.strip()
                    sl = s.lower()
                    if any(
                        sl.startswith(prefix)
                        for prefix in (
                            "router ospf",
                            "router rip",
                            "router eigrp",
                            "network ",
                            "ip dhcp ",
                            "default-router ",
                            "dns-server ",
                            "ip helper-address ",
                            "ip nat ",
                        )
                    ):
                        extra_cfg.append("    # " + s)

            block = header
            if if_lines:
                block += "\n" + "\n".join(if_lines)
            if extra_cfg:
                block += "\n" + "\n".join(extra_cfg[:25])
            dev_blocks.append(block)

        links = [
            f"- {l.source_device}:{l.source_interface} <--> {l.target_device}:{l.target_interface} ({l.link_type}, {l.status})"
            for l in topology.links
        ]
        summary = "Dispositivos y configuración actual:\n" + "\n".join(dev_blocks) + "\n\nEnlaces:\n" + "\n".join(links)

        if topology.activity_instructions:
            instr_text = "\n\n".join(
                f"[{p.get('title', 'Instrucciones')}]\n{p.get('text', '')}"
                for p in topology.activity_instructions
                if p.get("text")
            ).strip()
            if instr_text:
                summary += f"\n\n[INSTRUCCIONES DE LA ACTIVIDAD (.PKA)]\n{instr_text[:5000]}"
        return summary

    def _summarize_findings(self, report: DiagnosticReport, selected: Optional[DiagnosticFinding]) -> str:
        lines = []
        if selected:
            lines.append(
                f"HALLAZGO ENFOCADO: [{selected.severity.value.upper()}] {selected.device_name} "
                f"({selected.interface_name or 'global'}): {selected.title}\n"
                f"Detalle: {selected.description}\n"
                f"Referencia técnica del motor: {selected.technical_solution}"
            )
            other = [f for f in report.findings if f.id != selected.id]
            if other:
                lines.append("\nOtros hallazgos detectados en la topología:")
                for f in other[:10]:
                    lines.append(f"- [{f.severity.value.upper()}] {f.device_name} ({f.interface_name or 'global'}): {f.title}")
        else:
            for f in report.findings:
                lines.append(
                    f"- [{f.severity.value.upper()}] {f.device_name} ({f.interface_name or 'global'}): "
                    f"{f.title} -> {f.description}"
                )
        return "\n".join(lines) if lines else "No se detectaron hallazgos críticos por reglas deterministas."

ai_tutor_service = AITutorService()
