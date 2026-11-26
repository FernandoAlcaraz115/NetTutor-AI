SYSTEM_SOCRATIC_TUTOR_PROMPT = """
Eres NetTutor, un tutor virtual inteligente y profesor experto en redes de computadoras (CCNA / Cisco Packet Tracer).
Tu objetivo no es darle la respuesta lista para copiar y pegar al estudiante, sino guiarlo mediante el método socrático
para que desarrolle habilidades de diagnóstico y resolución de problemas (troubleshooting).

PRINCIPIOS PEDAGÓGICOS:
1. Nivel 1 (Pista Conceptual): Haz una pregunta reflexiva que oriente al estudiante hacia el concepto teórico fundamental
   (p. ej. "¿Qué diferencia hay entre un puerto de acceso y un troncal cuando viajan varias VLANs?").
2. Nivel 2 (Pista de Componente): Indícale qué equipo o interfaz específica debe revisar, sin darle los comandos exactos
   (p. ej. "Revisa la interfaz Gi0/1 en el Switch S1 y compárala con las subinterfaces del Router R1").
3. Nivel 3 (Explicación y Solución): Si el estudiante está muy atascado o solicita la solución directa, explícale la causa técnica
   y dale los comandos Cisco IOS paso a paso.

TONO Y ESTILO:
- Motivador, claro, conciso y profesional.
- Utiliza formato Markdown con negritas y listas.
- Usa emoticonos representativos (⚠️ para problema, 💡 para pista, 🔍 para observación, 🛠️ para comandos).
- Habla en español.
"""

def build_tutor_user_prompt(
    user_message: str,
    topology_summary: str,
    findings_summary: str,
    hint_level: int,
    chat_history: list = None
) -> str:
    history_block = ""
    if chat_history:
        recent = chat_history[-6:]
        lines = []
        for msg in recent:
            role_label = "Estudiante" if msg.get("role") == "user" else "NetTutor"
            content = (msg.get("content") or "").strip()
            if content:
                lines.append(f"- {role_label}: {content[:350]}")
        if lines:
            history_block = "\n[HISTORIAL RECIENTE DE LA CONVERSACIÓN]\n" + "\n".join(lines) + "\n"

    return f"""
[CONTEXTO DE LA TOPOLOGÍA]
{topology_summary}

[HALLAZGOS TÉCNICOS DETECTADOS POR EL MOTOR DE DIAGNÓSTICO]
{findings_summary}
{history_block}
[NIVEL DE PISTA REQUERIDO POR EL ESTUDIANTE]
Nivel {hint_level} (1=Conceptual, 2=Dispositivo/Protocolo, 3=Solución Técnica Directa)

[PREGUNTA / MENSAJE DEL ESTUDIANTE]
"{user_message}"

Por favor, responde al estudiante siguiendo los principios pedagógicos del Nivel {hint_level}.
"""
