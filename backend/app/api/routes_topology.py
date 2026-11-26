import base64
from pathlib import Path
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from app.core.config import settings
from app.core.models import Topology
from app.sample_labs.sample_data import get_sample_intervlan_lab
from app.parser.cisco_ios_parser import CiscoIOSParser
from app.parser.pkt_parser import PktParser

router = APIRouter(prefix="/topology", tags=["Topology"])

# Estado de la topología en memoria (para la sesión activa)
current_topology: Topology = get_sample_intervlan_lab()


def get_current_topology() -> Topology:
    """Obtiene la topología de red actualmente cargada en el tutor."""
    return current_topology


def set_current_topology(topology: Topology) -> Topology:
    """Actualiza la topología activa en memoria."""
    global current_topology
    current_topology = topology
    return current_topology


@router.get("", response_model=Topology)
def get_topology_endpoint():
    """Obtiene la topología de red actualmente cargada en el tutor."""
    return get_current_topology()


@router.post("", response_model=Topology)
def update_topology(topology: Topology):
    """Actualiza la topología completa."""
    return set_current_topology(topology)


@router.get("/presets")
def list_presets():
    """Lista los laboratorios predefinidos y los archivos .pkt en BANCO DE PRACTICAS."""
    presets = [
        {
            "id": "lab1_intervlan",
            "name": "Práctica Demo: Inter-VLAN Routing (Router-on-a-stick)",
            "difficulty": "Intermedio",
            "source": "builtin",
            "description": "Configuración de subinterfaces dot1q, trunks y asignación de gateways.",
        }
    ]

    if settings.PRACTICES_DIR.exists():
        pkt_files = sorted(
            [p for p in settings.PRACTICES_DIR.iterdir() if p.is_file() and p.suffix.lower() in (".pkt", ".pka")],
            key=lambda p: p.name.lower(),
        )
        for pkt_file in pkt_files:
            ext_label = pkt_file.suffix.upper().lstrip(".")
            presets.append(
                {
                    "id": f"pkt:{pkt_file.name}",
                    "name": f"📦 [{ext_label}] {pkt_file.stem}",
                    "difficulty": f"Packet Tracer ({pkt_file.suffix.lower()})",
                    "source": "pkt_bank",
                    "filename": pkt_file.name,
                    "description": f"Archivo real de Cisco Packet Tracer ({pkt_file.name}) en BANCO DE PRACTICAS.",
                }
            )

    return presets


@router.post("/presets/{preset_id:path}/load", response_model=Topology)
def load_preset(preset_id: str):
    """Carga una práctica predefinida o un archivo .pkt del BANCO DE PRACTICAS."""
    global current_topology

    # Decodificar URL en caso de que venga codificada (%3A, %20, etc.)
    import urllib.parse
    preset_id = urllib.parse.unquote(preset_id)

    if preset_id == "lab1_intervlan":
        return set_current_topology(get_sample_intervlan_lab())

    if preset_id.startswith("pkt:"):
        filename = preset_id.split("pkt:", 1)[1].strip()
        practices_root = settings.PRACTICES_DIR.resolve()
        pkt_path = (practices_root / filename).resolve()
        if practices_root not in pkt_path.parents:
            raise HTTPException(status_code=400, detail="Ruta de archivo inválida.")
        if not pkt_path.exists():
            raise HTTPException(status_code=404, detail=f"Archivo '{filename}' no encontrado en BANCO DE PRACTICAS")
        try:
            return set_current_topology(PktParser.parse_file(pkt_path))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error al desencriptar/parsear '{filename}': {e}")

    raise HTTPException(status_code=404, detail="Preset no encontrado")


@router.post("/load-by-id", response_model=Topology)
def load_preset_by_payload(payload: Dict[str, str]):
    """Carga alternativa vía JSON payload para evitar problemas de codificación en URLs."""
    preset_id = payload.get("preset_id", "")
    return load_preset(preset_id)


@router.post("/upload-pkt", response_model=Topology)
def upload_pkt_file(payload: Dict[str, str]):
    """
    Recibe un archivo .pkt codificado en Base64 desde el navegador, lo desencripta
    mediante el pipeline Twofish-EAX + zlib y carga la topología resultante.
    """
    filename = payload.get("filename", "Practica_Subida.pkt")
    b64_data = payload.get("content_base64", "")
    if not b64_data:
        raise HTTPException(status_code=400, detail="content_base64 es requerido")

    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]

    try:
        raw_bytes = base64.b64decode(b64_data)
        if len(raw_bytes) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="El archivo supera el tamaño máximo permitido (25 MB).")
        parsed_topo = PktParser.parse_bytes(raw_bytes, filename=filename)
        return set_current_topology(parsed_topo)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo desencriptar el archivo .pkt/.pka: {e}")


@router.post("/import-config")
def import_cisco_config(payload: Dict[str, str]):
    """
    Parsea una configuración 'show running-config' de Cisco IOS
    y la integra a la topología activa.
    """
    config_text = payload.get("config_text", "")
    if not config_text:
        raise HTTPException(status_code=400, detail="config_text es requerido")

    parsed_device = CiscoIOSParser.parse_config(config_text)

    global current_topology
    existing_idx = next(
        (i for i, d in enumerate(current_topology.devices) if d.name.lower() == parsed_device.name.lower()),
        None,
    )
    if existing_idx is not None:
        existing_dev = current_topology.devices[existing_idx]
        parsed_device.id = existing_dev.id
        parsed_device.pos_x = existing_dev.pos_x
        parsed_device.pos_y = existing_dev.pos_y
        current_topology.devices[existing_idx] = parsed_device
    else:
        current_topology.devices.append(parsed_device)

    return {
        "message": f"Dispositivo '{parsed_device.name}' parseado e integrado con éxito",
        "device": parsed_device,
    }
