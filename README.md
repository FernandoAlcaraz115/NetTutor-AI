# ⚡ NetTutorIA - Laboratorio Inteligente de Redes y Tutor Socrático

**NetTutorIA** es un asistente y tutor pedagógico inteligente diseñado para prácticas de redes (Cisco Packet Tracer). 

A diferencia de los evaluadores convencionales como el *Activity Wizard* de Packet Tracer —que únicamente devuelven un porcentaje o un frío *"Configuración incorrecta"*—, **NetTutorIA** comprende la topología, identifica la causa raíz de las fallas de red y guía al estudiante con **pistas adaptativas por niveles socráticos**.

---

## 🎯 Ejemplo de Retroalimentación

| Evaluador Estándar | NetTutorIA |
| :--- | :--- |
| ❌ *Configuración de enlace 0%* | ⚠️ **Problema en S1**: El puerto `Fa0/1` está configurado como modo acceso, pero se conecta al router `R1` que posee subinterfaces 802.1Q.<br><br>💡 **Pista Nivel 1 (Conceptual):** *"¿Qué tipo de enlace de switch necesitas cuando un mismo cable debe transportar el tráfico de múltiples VLANs hacia un router?"*<br><br>🔍 **Pista Nivel 2 (Componente):** *"Revisa la interfaz Fa0/1 de S1 y la configuración de subinterfaces en R1."*<br><br>🛠️ **Pista Nivel 3 (Solución técnica):** `switchport mode trunk` |

---

## 🏗️ Arquitectura del Sistema

```
NetTutorIA/
├── backend/
│   ├── app/
│   │   ├── api/                     # Endpoints REST (FastAPI)
│   │   │   ├── routes_diagnostics.py # Ejecución de reglas y reportes
│   │   │   ├── routes_tutor.py       # Chat socrático y pistas adaptativas
│   │   │   ├── routes_topology.py    # Gestión e importación de topologías
│   │   │   └── routes_packet_tracer.py # Conexión IPC con Packet Tracer
│   │   ├── core/                    # Modelos Pydantic y configuraciones
│   │   ├── engine/                  # Motor de consistencia y reglas de red
│   │   │   ├── rules/               # Reglas deterministas L1, L2 y L3
│   │   │   │   ├── vlan_trunk_rules.py
│   │   │   │   ├── ip_subnet_rules.py
│   │   │   │   ├── gateway_rules.py
│   │   │   │   └── interface_status_rules.py
│   │   │   └── rule_engine.py       # Orquestador del análisis de red
│   │   ├── parser/                  # Parser de Cisco IOS running-config
│   │   ├── tutor/                   # Servicio de IA con Gemini + fallback heurístico
│   │   ├── sample_labs/             # Laboratorios piloto predefinidos
│   │   └── main.py                  # Entrypoint de FastAPI y montaje estático
│   ├── requirements.txt
│   └── run.py                       # Script de ejecución del servidor
├── frontend/
│   ├── index.html                   # Dashboard interactivo principal
│   ├── css/
│   │   └── style.css                # Estilo moderno oscuro con glassmorphism
│   └── js/
│       ├── app.js                   # Controlador central de la aplicación
│       ├── api.js                   # Cliente HTTP
│       ├── topology_viewer.js       # Renderizado interactivo SVG de topología
│       ├── tutor_chat.js            # Chat socrático con niveles de pista
│       └── diagnostics_panel.js     # Lista de hallazgos técnicos
├── .env.example
└── README.md
```

---

## 🚀 Puesta en Marcha

### 1. Requisitos Previos
* **Python 3.10+** (Probado en Python 3.11)

### 2. Instalación de dependencias
```bash
pip install -r backend/requirements.txt
```

### 3. Configuración de Variables de Entorno (Opcional)
Copia `.env.example` a `.env`:
```bash
cp .env.example .env
```
* Si agregas tu `GEMINI_API_KEY`, NetTutor utilizará el modelo de lenguaje de Google para conversar fluidamente y contextualizar las explicaciones.
* Si **no** agregas clave de API, NetTutor funciona en **modo offline/heurístico**, entregando todas las pistas socráticas y diagnósticos técnicos con las reglas preprogramadas.

### 4. Iniciar la Aplicación Web
```bash
python backend/run.py
```
Abre tu navegador en:
👉 **http://localhost:8000**

Documentación interactiva de la API:
👉 **http://localhost:8000/docs**

---

## 🔌 Integración con Cisco Packet Tracer

1. **Vía IPC en vivo:** En Packet Tracer, activa el servicio en `Extensions > IPC` (puerto por defecto `39000`). NetTutorIA detectará el servicio automáticamente.
2. **Vía `show running-config`:** Haz clic en el botón **"📋 Importar Config"** en la barra superior para pegar la configuración de cualquier switch o router. NetTutorIA parseará las interfaces, subredes, VLANs y enlaces al instante.
