"""
Endpoints REST para Simulación de Ping y Terminal CLI Cisco IOS interactiva.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from pydantic import BaseModel

from app.api.routes_topology import get_current_topology
from app.engine.network_simulator import NetworkSimulator, PingSimulationResult
from app.engine.cisco_ios_emulator import CiscoIOSEmulator, CommandExecutionRequest, CommandExecutionResponse

router = APIRouter(prefix="/tools", tags=["Tools"])


class PingRequest(BaseModel):
    source_device_id: str
    target_device_id: str


@router.post("/ping", response_model=PingSimulationResult)
def run_ping_simulation(req: PingRequest):
    """
    Ejecuta una simulación de Ping e inspecciona la ruta hop-a-hop
    en Capa 1, 2 y 3 informando en qué punto exacto ocurre un fallo si lo hay.
    """
    curr_topo = get_current_topology()
    result = NetworkSimulator.simulate_ping(
        topology=curr_topo,
        source_id=req.source_device_id,
        target_id=req.target_device_id
    )
    return result


@router.post("/cli/execute", response_model=CommandExecutionResponse)
def execute_cli_command(req: CommandExecutionRequest):
    """
    Ejecuta un comando Cisco IOS (enable, conf t, interface, switchport, ip address, no shut, etc.)
    sobre un dispositivo en vivo, modificando la topología y recalculando la consistencia.
    """
    curr_topo = get_current_topology()
    dev = next((d for d in curr_topo.devices if d.id == req.device_id or d.name.lower() == req.device_id.lower()), None)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Dispositivo '{req.device_id}' no encontrado")

    resp = CiscoIOSEmulator.execute(dev, req)
    return resp

