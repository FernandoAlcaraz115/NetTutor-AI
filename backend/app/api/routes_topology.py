from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from app.core.models import Topology
from app.sample_labs.sample_data import get_sample_intervlan_lab
from app.parser.cisco_ios_parser import CiscoIOSParser

router = APIRouter(prefix="/topology", tags=["Topology"])

# Estado de la topología en memoria (para la sesión activa)
current_topology: Topology = get_sample_intervlan_lab()

@router.get("", response_model=Topology)
def get_current_topology():
    """Obtiene la topología de red actualmente cargada en el tutor."""
    return current_topology

@router.post("", response_model=Topology)
def update_topology(topology: Topology):
    """Actualiza la topología completa."""
    global current_topology
    current_topology = topology
    return current_topology

@router.get("/presets")
def list_presets():
    """Lista los laboratorios de prueba disponibles."""
    return [
        {
            "id": "lab1_intervlan",
            "name": "Práctica 1: Inter-VLAN Routing (Router-on-a-stick)",
            "difficulty": "Intermedio",
            "description": "Configuración de subinterfaces dot1q, trunks y asignación de gateways."
        }
    ]

@router.post("/presets/{preset_id}/load", response_model=Topology)
def load_preset(preset_id: str):
    """Carga una práctica predefinida."""
    global current_topology
    if preset_id == "lab1_intervlan":
        current_topology = get_sample_intervlan_lab()
        return current_topology
    raise HTTPException(status_code=404, detail="Preset no encontrado")

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
    # Si el dispositivo ya existe, reemplazarlo; si no, agregarlo
    existing_idx = next((i for i, d in enumerate(current_topology.devices) if d.name.lower() == parsed_device.name.lower()), None)
    if existing_idx is not None:
        current_topology.devices[existing_idx] = parsed_device
    else:
        current_topology.devices.append(parsed_device)

    return {
        "message": f"Dispositivo '{parsed_device.name}' parseado e integrado con éxito",
        "device": parsed_device
    }
