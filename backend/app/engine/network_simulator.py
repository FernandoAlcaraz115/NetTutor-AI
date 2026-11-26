"""
Motor de Simulación de Conectividad (Ping & Traceroute) para NetTutorIA.
Evalúa el recorrido salto a salto entre dos dispositivos considerando:
  - Capa 1: Estado físico/administrativo de interfaces y enlaces.
  - Capa 2: Enlaces Access, VLANs coincidentes, Trunks 802.1Q, Native VLAN y Allowed VLANs.
  - Capa 3: Subredes locales, Default Gateways (origen y destino), Router-on-a-stick y Subinterfaces.
"""

import ipaddress
import re
from collections import deque
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel
from app.core.models import (
    Topology,
    Device,
    DeviceType,
    Interface,
    Link,
    SwitchportMode,
    InterfaceStatus,
)


class SimulationHop(BaseModel):
    step: int
    device_id: str
    device_name: str
    device_type: str
    in_interface: Optional[str] = None
    out_interface: Optional[str] = None
    status: str  # "forwarded", "dropped", "reached"
    message: str


class PingSimulationResult(BaseModel):
    success: bool
    source_device: str
    target_device: str
    source_ip: str
    target_ip: str
    hops: List[SimulationHop]
    failure_reason: Optional[str] = None
    failure_layer: Optional[str] = None
    path_links: List[str] = []  # IDs de los enlaces recorridos para animación


def _canonical_if_name(name: str) -> str:
    """Normaliza nombres de interfaces Cisco (Fa0/1 <-> FastEthernet0/1, Gi0/1 <-> GigabitEthernet0/1)."""
    n = (name or "").strip().lower().replace(" ", "")
    n = re.sub(r"^fastethernet", "fa", n)
    n = re.sub(r"^gigabitethernet", "gi", n)
    n = re.sub(r"^tengigabitethernet", "te", n)
    n = re.sub(r"^ethernet", "eth", n)
    n = re.sub(r"^serial", "se", n)
    n = re.sub(r"^loopback", "lo", n)
    return n


def _find_interface(device: Device, port_name: str) -> Optional[Interface]:
    target = _canonical_if_name(port_name)
    for iface in device.interfaces:
        if iface.name == port_name or _canonical_if_name(iface.name) == target:
            return iface
    return None


class NetworkSimulator:

    @classmethod
    def simulate_ping(cls, topology: Topology, source_id: str, target_id: str) -> PingSimulationResult:
        device_map = {d.id: d for d in topology.devices}
        src_dev = device_map.get(source_id)
        tgt_dev = device_map.get(target_id)

        if not src_dev or not tgt_dev:
            return PingSimulationResult(
                success=False,
                source_device=source_id,
                target_device=target_id,
                source_ip="",
                target_ip="",
                hops=[],
                failure_reason="Dispositivo de origen o destino no encontrado en la topología.",
                failure_layer="L1",
            )

        if src_dev.id == tgt_dev.id:
            src_ip, _ = cls._get_device_ip_mask(src_dev)
            return PingSimulationResult(
                success=True,
                source_device=src_dev.name,
                target_device=tgt_dev.name,
                source_ip=src_ip or "127.0.0.1",
                target_ip=src_ip or "127.0.0.1",
                hops=[
                    SimulationHop(
                        step=1,
                        device_id=src_dev.id,
                        device_name=src_dev.name,
                        device_type=src_dev.type.value,
                        status="reached",
                        message=f"Loopback local exitoso en {src_dev.name} ({src_ip or '127.0.0.1'}).",
                    )
                ],
                path_links=[],
            )

        src_ip, src_mask = cls._get_device_ip_mask(src_dev)
        tgt_ip, tgt_mask = cls._get_device_ip_mask(tgt_dev)

        if not src_ip:
            return PingSimulationResult(
                success=False,
                source_device=src_dev.name,
                target_device=tgt_dev.name,
                source_ip="",
                target_ip=tgt_ip or "",
                hops=[],
                failure_reason=f"{src_dev.name} no tiene dirección IP configurada.",
                failure_layer="L3",
            )

        if not tgt_ip:
            return PingSimulationResult(
                success=False,
                source_device=src_dev.name,
                target_device=tgt_dev.name,
                source_ip=src_ip,
                target_ip="",
                hops=[],
                failure_reason=f"{tgt_dev.name} no tiene dirección IP configurada.",
                failure_layer="L3",
            )

        hops: List[SimulationHop] = [
            SimulationHop(
                step=1,
                device_id=src_dev.id,
                device_name=src_dev.name,
                device_type=src_dev.type.value,
                in_interface=None,
                out_interface=cls._get_first_up_interface(src_dev),
                status="forwarded",
                message=f"Generando paquete ICMP Echo Request desde {src_dev.name} ({src_ip}) hacia {tgt_ip}.",
            )
        ]

        # Verificar si origen y destino están en la misma subred
        same_subnet = False
        net_src = None
        net_tgt = None
        try:
            net_src = ipaddress.IPv4Network(f"{src_ip}/{src_mask}", strict=False)
            net_tgt = ipaddress.IPv4Network(f"{tgt_ip}/{tgt_mask}", strict=False)
            same_subnet = (net_src == net_tgt)
        except Exception:
            pass

        # Si están en diferente subred, validar Default Gateway del origen y buscar ruta vía Router
        if not same_subnet:
            if src_dev.type in (DeviceType.PC, DeviceType.SERVER):
                if not src_dev.default_gateway:
                    hops.append(
                        SimulationHop(
                            step=len(hops) + 1,
                            device_id=src_dev.id,
                            device_name=src_dev.name,
                            device_type=src_dev.type.value,
                            status="dropped",
                            message=f"Falla Capa 3: {src_dev.name} necesita enviar a otra subred ({tgt_ip}) pero no tiene Default Gateway configurado.",
                        )
                    )
                    return PingSimulationResult(
                        success=False,
                        source_device=src_dev.name,
                        target_device=tgt_dev.name,
                        source_ip=src_ip,
                        target_ip=tgt_ip,
                        hops=hops,
                        failure_reason=f"Default Gateway ausente en {src_dev.name}.",
                        failure_layer="L3",
                    )

                # Validar que el gateway pertenezca a la subred local del origen
                if net_src is not None:
                    try:
                        if ipaddress.IPv4Address(src_dev.default_gateway) not in net_src:
                            hops.append(
                                SimulationHop(
                                    step=len(hops) + 1,
                                    device_id=src_dev.id,
                                    device_name=src_dev.name,
                                    device_type=src_dev.type.value,
                                    status="dropped",
                                    message=(
                                        f"Falla Capa 3: El Default Gateway de {src_dev.name} ({src_dev.default_gateway}) "
                                        f"está fuera de su subred local ({net_src})."
                                    ),
                                )
                            )
                            return PingSimulationResult(
                                success=False,
                                source_device=src_dev.name,
                                target_device=tgt_dev.name,
                                source_ip=src_ip,
                                target_ip=tgt_ip,
                                hops=hops,
                                failure_reason=f"Default Gateway de {src_dev.name} fuera de subred.",
                                failure_layer="L3",
                            )
                    except ValueError:
                        pass

            # Localizar router que atiende el gateway del origen (o cualquier router alcanzable)
            gateway_router = cls._find_router_for_ip(topology, src_dev.default_gateway) if src_dev.default_gateway else None
            if not gateway_router:
                routers = [d for d in topology.devices if d.type == DeviceType.ROUTER]
                gateway_router = routers[0] if routers else None

            if not gateway_router:
                hops.append(
                    SimulationHop(
                        step=len(hops) + 1,
                        device_id=src_dev.id,
                        device_name=src_dev.name,
                        device_type=src_dev.type.value,
                        status="dropped",
                        message=(
                            f"Falla Capa 3: {src_dev.name} ({src_ip}) y {tgt_dev.name} ({tgt_ip}) están en subredes distintas, "
                            f"pero no existe ningún Router en la topología para enrutar el tráfico."
                        ),
                    )
                )
                return PingSimulationResult(
                    success=False,
                    source_device=src_dev.name,
                    target_device=tgt_dev.name,
                    source_ip=src_ip,
                    target_ip=tgt_ip,
                    hops=hops,
                    failure_reason="Subredes diferentes sin equipo de Capa 3 (Router).",
                    failure_layer="L3",
                )

            # Construir ruta en dos tramos: origen -> router (L2) y router -> destino (L2/L3)
            seg1 = cls._bfs_path(topology, src_dev.id, gateway_router.id)
            if not seg1:
                hops.append(
                    SimulationHop(
                        step=len(hops) + 1,
                        device_id=src_dev.id,
                        device_name=src_dev.name,
                        device_type=src_dev.type.value,
                        status="dropped",
                        message=f"Falla Capa 1: No existe camino físico desde {src_dev.name} hasta el router {gateway_router.name}.",
                    )
                )
                return PingSimulationResult(
                    success=False,
                    source_device=src_dev.name,
                    target_device=tgt_dev.name,
                    source_ip=src_ip,
                    target_ip=tgt_ip,
                    hops=hops,
                    failure_reason=f"Sin enlace físico hacia el router {gateway_router.name}.",
                    failure_layer="L1",
                )

            seg2 = cls._bfs_path(topology, gateway_router.id, tgt_dev.id)
            if not seg2:
                hops.append(
                    SimulationHop(
                        step=len(hops) + 1,
                        device_id=gateway_router.id,
                        device_name=gateway_router.name,
                        device_type=gateway_router.type.value,
                        status="dropped",
                        message=f"Falla Capa 1: El router {gateway_router.name} no tiene ruta física hacia {tgt_dev.name}.",
                    )
                )
                return PingSimulationResult(
                    success=False,
                    source_device=src_dev.name,
                    target_device=tgt_dev.name,
                    source_ip=src_ip,
                    target_ip=tgt_ip,
                    hops=hops,
                    failure_reason=f"Sin enlace físico desde {gateway_router.name} hacia {tgt_dev.name}.",
                    failure_layer="L1",
                )

            path_links: List[str] = []

            # Evaluar Tramo 1: Origen -> Router
            ok1, err_reason, err_layer, src_vlan = cls._evaluate_segment(
                device_map=device_map,
                path_devices=seg1[0],
                path_links_objs=seg1[1],
                hops=hops,
                path_links_ids=path_links,
                is_final_segment=False,
                target_ip=None,
            )
            if not ok1:
                return PingSimulationResult(
                    success=False,
                    source_device=src_dev.name,
                    target_device=tgt_dev.name,
                    source_ip=src_ip,
                    target_ip=tgt_ip,
                    hops=hops,
                    path_links=path_links,
                    failure_reason=err_reason,
                    failure_layer=err_layer,
                )

            # Verificar que el router efectivamente tenga la IP del gateway del origen
            if src_dev.type in (DeviceType.PC, DeviceType.SERVER) and src_dev.default_gateway:
                router_has_gw = any(i.ip_address == src_dev.default_gateway for i in gateway_router.interfaces)
                if not router_has_gw:
                    hops.append(
                        SimulationHop(
                            step=len(hops) + 1,
                            device_id=gateway_router.id,
                            device_name=gateway_router.name,
                            device_type=gateway_router.type.value,
                            status="dropped",
                            message=(
                                f"Falla Capa 3: El paquete llegó a {gateway_router.name}, pero ninguna interfaz/subinterfaz "
                                f"tiene configurada la IP de gateway {src_dev.default_gateway}."
                            ),
                        )
                    )
                    return PingSimulationResult(
                        success=False,
                        source_device=src_dev.name,
                        target_device=tgt_dev.name,
                        source_ip=src_ip,
                        target_ip=tgt_ip,
                        hops=hops,
                        path_links=path_links,
                        failure_reason=f"Gateway {src_dev.default_gateway} no configurado en {gateway_router.name}.",
                        failure_layer="L3",
                    )

            # Evaluar Tramo 2: Router -> Destino
            ok2, err_reason, err_layer, _ = cls._evaluate_segment(
                device_map=device_map,
                path_devices=seg2[0],
                path_links_objs=seg2[1],
                hops=hops,
                path_links_ids=path_links,
                is_final_segment=True,
                target_ip=tgt_ip,
            )
            if not ok2:
                return PingSimulationResult(
                    success=False,
                    source_device=src_dev.name,
                    target_device=tgt_dev.name,
                    source_ip=src_ip,
                    target_ip=tgt_ip,
                    hops=hops,
                    path_links=path_links,
                    failure_reason=err_reason,
                    failure_layer=err_layer,
                )

            # Verificar Default Gateway del destino para el Echo Reply
            if tgt_dev.type in (DeviceType.PC, DeviceType.SERVER):
                if not tgt_dev.default_gateway:
                    hops.append(
                        SimulationHop(
                            step=len(hops) + 1,
                            device_id=tgt_dev.id,
                            device_name=tgt_dev.name,
                            device_type=tgt_dev.type.value,
                            status="dropped",
                            message=(
                                f"Falla Capa 3 (Echo Reply): El paquete llegó a {tgt_dev.name}, pero no puede responder "
                                f"a otra subred porque no tiene Default Gateway configurado."
                            ),
                        )
                    )
                    return PingSimulationResult(
                        success=False,
                        source_device=src_dev.name,
                        target_device=tgt_dev.name,
                        source_ip=src_ip,
                        target_ip=tgt_ip,
                        hops=hops,
                        path_links=path_links,
                        failure_reason=f"Default Gateway ausente en {tgt_dev.name} (falla el retorno ICMP).",
                        failure_layer="L3",
                    )
                if net_tgt is not None:
                    try:
                        if ipaddress.IPv4Address(tgt_dev.default_gateway) not in net_tgt:
                            hops.append(
                                SimulationHop(
                                    step=len(hops) + 1,
                                    device_id=tgt_dev.id,
                                    device_name=tgt_dev.name,
                                    device_type=tgt_dev.type.value,
                                    status="dropped",
                                    message=(
                                        f"Falla Capa 3 (Echo Reply): El Default Gateway de {tgt_dev.name} "
                                        f"({tgt_dev.default_gateway}) está fuera de su subred ({net_tgt})."
                                    ),
                                )
                            )
                            return PingSimulationResult(
                                success=False,
                                source_device=src_dev.name,
                                target_device=tgt_dev.name,
                                source_ip=src_ip,
                                target_ip=tgt_ip,
                                hops=hops,
                                path_links=path_links,
                                failure_reason=f"Default Gateway de {tgt_dev.name} fuera de subred.",
                                failure_layer="L3",
                            )
                    except ValueError:
                        pass

            hops.append(
                SimulationHop(
                    step=len(hops) + 1,
                    device_id=tgt_dev.id,
                    device_name=tgt_dev.name,
                    device_type=tgt_dev.type.value,
                    status="reached",
                    message=f"¡Éxito! Paquete ICMP Echo Reply recibido satisfactoriamente desde {tgt_dev.name} ({tgt_ip}) vía {gateway_router.name}.",
                )
            )
            return PingSimulationResult(
                success=True,
                source_device=src_dev.name,
                target_device=tgt_dev.name,
                source_ip=src_ip,
                target_ip=tgt_ip,
                hops=hops,
                path_links=path_links,
            )

        # Caso misma subred: BFS directo (Capa 1 y Capa 2)
        direct_path = cls._bfs_path(topology, src_dev.id, tgt_dev.id)
        if not direct_path:
            hops.append(
                SimulationHop(
                    step=len(hops) + 1,
                    device_id=src_dev.id,
                    device_name=src_dev.name,
                    device_type=src_dev.type.value,
                    status="dropped",
                    message=f"No existe ninguna ruta física de cables entre {src_dev.name} y {tgt_dev.name}.",
                )
            )
            return PingSimulationResult(
                success=False,
                source_device=src_dev.name,
                target_device=tgt_dev.name,
                source_ip=src_ip,
                target_ip=tgt_ip,
                hops=hops,
                failure_reason="Aislamiento físico: No hay enlace entre los extremos.",
                failure_layer="L1",
            )

        path_links = []
        ok, err_reason, err_layer, _ = cls._evaluate_segment(
            device_map=device_map,
            path_devices=direct_path[0],
            path_links_objs=direct_path[1],
            hops=hops,
            path_links_ids=path_links,
            is_final_segment=True,
            target_ip=tgt_ip,
        )
        if not ok:
            return PingSimulationResult(
                success=False,
                source_device=src_dev.name,
                target_device=tgt_dev.name,
                source_ip=src_ip,
                target_ip=tgt_ip,
                hops=hops,
                path_links=path_links,
                failure_reason=err_reason,
                failure_layer=err_layer,
            )

        hops.append(
            SimulationHop(
                step=len(hops) + 1,
                device_id=tgt_dev.id,
                device_name=tgt_dev.name,
                device_type=tgt_dev.type.value,
                status="reached",
                message=f"¡Éxito! Paquete ICMP Echo Reply recibido satisfactoriamente desde {tgt_dev.name} ({tgt_ip}).",
            )
        )
        return PingSimulationResult(
            success=True,
            source_device=src_dev.name,
            target_device=tgt_dev.name,
            source_ip=src_ip,
            target_ip=tgt_ip,
            hops=hops,
            path_links=path_links,
        )

    @classmethod
    def _evaluate_segment(
        cls,
        device_map: Dict[str, Device],
        path_devices: List[str],
        path_links_objs: List[Link],
        hops: List[SimulationHop],
        path_links_ids: List[str],
        is_final_segment: bool,
        target_ip: Optional[str],
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[int]]:
        """
        Evalúa un segmento L1/L2 salto a salto.
        Retorna: (ok, failure_reason, failure_layer, active_vlan)
        """
        current_vlan: Optional[int] = None

        for i, link in enumerate(path_links_objs):
            d_curr = device_map[path_devices[i]]
            d_next = device_map[path_devices[i + 1]]
            path_links_ids.append(link.id)

            curr_port = link.source_interface if link.source_device == d_curr.id else link.target_interface
            next_port = link.target_interface if link.source_device == d_curr.id else link.source_interface

            curr_if = _find_interface(d_curr, curr_port)
            next_if = _find_interface(d_next, next_port)

            # 1. Capa 1: Estado de enlace e interfaces
            if link.status == "down":
                hops.append(
                    SimulationHop(
                        step=len(hops) + 1,
                        device_id=d_curr.id,
                        device_name=d_curr.name,
                        device_type=d_curr.type.value,
                        out_interface=curr_port,
                        status="dropped",
                        message=f"Falla Capa 1: El enlace físico entre {d_curr.name} ({curr_port}) y {d_next.name} ({next_port}) está caído.",
                    )
                )
                return False, f"Enlace físico caído entre {d_curr.name} y {d_next.name}.", "L1", current_vlan

            if curr_if and curr_if.status == InterfaceStatus.ADMIN_DOWN:
                hops.append(
                    SimulationHop(
                        step=len(hops) + 1,
                        device_id=d_curr.id,
                        device_name=d_curr.name,
                        device_type=d_curr.type.value,
                        out_interface=curr_port,
                        status="dropped",
                        message=f"Falla Capa 1: La interfaz {curr_port} en {d_curr.name} está apagada ('administratively down').",
                    )
                )
                return False, f"Puerto {curr_port} en {d_curr.name} apagado.", "L1", current_vlan

            if next_if and next_if.status == InterfaceStatus.ADMIN_DOWN:
                hops.append(
                    SimulationHop(
                        step=len(hops) + 1,
                        device_id=d_next.id,
                        device_name=d_next.name,
                        device_type=d_next.type.value,
                        in_interface=next_port,
                        status="dropped",
                        message=f"Falla Capa 1: La interfaz de entrada {next_port} en {d_next.name} está apagada ('administratively down').",
                    )
                )
                return False, f"Puerto {next_port} en {d_next.name} apagado.", "L1", current_vlan

            # 2. Capa 2: Host -> Switch (asigna la VLAN de entrada del puerto access)
            if d_curr.type in (DeviceType.PC, DeviceType.SERVER) and d_next.type == DeviceType.SWITCH:
                if next_if and next_if.switchport_mode == SwitchportMode.ACCESS:
                    current_vlan = next_if.access_vlan or 1
                else:
                    current_vlan = 1

            # Switch -> Host (el puerto de salida debe pertenecer a la misma VLAN del tráfico)
            elif d_curr.type == DeviceType.SWITCH and d_next.type in (DeviceType.PC, DeviceType.SERVER):
                port_vlan = (curr_if.access_vlan or 1) if (curr_if and curr_if.switchport_mode == SwitchportMode.ACCESS) else 1
                if current_vlan is not None and port_vlan != current_vlan:
                    hops.append(
                        SimulationHop(
                            step=len(hops) + 1,
                            device_id=d_curr.id,
                            device_name=d_curr.name,
                            device_type=d_curr.type.value,
                            out_interface=curr_port,
                            status="dropped",
                            message=(
                                f"Falla Capa 2: Aislamiento de VLAN en {d_curr.name}. El tráfico pertenece a la VLAN {current_vlan}, "
                                f"pero el puerto {curr_port} hacia {d_next.name} está en VLAN {port_vlan}."
                            ),
                        )
                    )
                    return False, f"Aislamiento de VLAN (VLAN {current_vlan} vs VLAN {port_vlan}).", "L2", current_vlan

            # Switch <-> Switch (Verificar Trunk, Native VLAN y Allowed VLANs)
            elif d_curr.type == DeviceType.SWITCH and d_next.type == DeviceType.SWITCH:
                if curr_if and next_if:
                    if (curr_if.switchport_mode == SwitchportMode.TRUNK) != (next_if.switchport_mode == SwitchportMode.TRUNK):
                        hops.append(
                            SimulationHop(
                                step=len(hops) + 1,
                                device_id=d_curr.id,
                                device_name=d_curr.name,
                                device_type=d_curr.type.value,
                                out_interface=curr_port,
                                status="dropped",
                                message=(
                                    f"Falla Capa 2: Desajuste de modo Trunk/Access entre {d_curr.name} ({curr_port}: {curr_if.switchport_mode.value}) "
                                    f"y {d_next.name} ({next_port}: {next_if.switchport_mode.value})."
                                ),
                            )
                        )
                        return False, f"Desajuste Trunk/Access entre {d_curr.name} y {d_next.name}.", "L2", current_vlan

                    if curr_if.switchport_mode == SwitchportMode.TRUNK and next_if.switchport_mode == SwitchportMode.TRUNK:
                        nat1 = curr_if.native_vlan or 1
                        nat2 = next_if.native_vlan or 1
                        if nat1 != nat2:
                            hops.append(
                                SimulationHop(
                                    step=len(hops) + 1,
                                    device_id=d_curr.id,
                                    device_name=d_curr.name,
                                    device_type=d_curr.type.value,
                                    out_interface=curr_port,
                                    status="dropped",
                                    message=f"Falla Capa 2: Native VLAN Mismatch entre {d_curr.name} (VLAN {nat1}) y {d_next.name} (VLAN {nat2}).",
                                )
                            )
                            return False, f"Native VLAN Mismatch entre {d_curr.name} y {d_next.name}.", "L2", current_vlan

                        if current_vlan is not None:
                            if curr_if.trunk_allowed_vlans is not None and current_vlan not in curr_if.trunk_allowed_vlans:
                                hops.append(
                                    SimulationHop(
                                        step=len(hops) + 1,
                                        device_id=d_curr.id,
                                        device_name=d_curr.name,
                                        device_type=d_curr.type.value,
                                        out_interface=curr_port,
                                        status="dropped",
                                        message=f"Falla Capa 2: El troncal {curr_port} en {d_curr.name} bloquea la VLAN {current_vlan} (allowed: {curr_if.trunk_allowed_vlans}).",
                                    )
                                )
                                return False, f"VLAN {current_vlan} bloqueada en troncal {d_curr.name}:{curr_port}.", "L2", current_vlan
                            if next_if.trunk_allowed_vlans is not None and current_vlan not in next_if.trunk_allowed_vlans:
                                hops.append(
                                    SimulationHop(
                                        step=len(hops) + 1,
                                        device_id=d_next.id,
                                        device_name=d_next.name,
                                        device_type=d_next.type.value,
                                        in_interface=next_port,
                                        status="dropped",
                                        message=f"Falla Capa 2: El troncal {next_port} en {d_next.name} bloquea la VLAN {current_vlan} (allowed: {next_if.trunk_allowed_vlans}).",
                                    )
                                )
                                return False, f"VLAN {current_vlan} bloqueada en troncal {d_next.name}:{next_port}.", "L2", current_vlan
                    elif curr_if.switchport_mode == SwitchportMode.ACCESS and next_if.switchport_mode == SwitchportMode.ACCESS:
                        v1 = curr_if.access_vlan or 1
                        v2 = next_if.access_vlan or 1
                        if current_vlan is not None and (v1 != current_vlan or v2 != current_vlan):
                            hops.append(
                                SimulationHop(
                                    step=len(hops) + 1,
                                    device_id=d_curr.id,
                                    device_name=d_curr.name,
                                    device_type=d_curr.type.value,
                                    out_interface=curr_port,
                                    status="dropped",
                                    message=f"Falla Capa 2: El enlace entre {d_curr.name} y {d_next.name} no es troncal y no transporta la VLAN {current_vlan}.",
                                )
                            )
                            return False, f"Enlace entre {d_curr.name} y {d_next.name} requiere modo trunk.", "L2", current_vlan

            # Switch -> Router (Router-on-a-stick o puerto dedicado)
            elif d_curr.type == DeviceType.SWITCH and d_next.type == DeviceType.ROUTER:
                base_r_if = _canonical_if_name(next_port.split(".")[0])
                subifs = [
                    iface for iface in d_next.interfaces
                    if _canonical_if_name(iface.name).startswith(base_r_if + ".") and iface.encapsulation_dot1q is not None
                ]
                if subifs:
                    if not curr_if or curr_if.switchport_mode != SwitchportMode.TRUNK:
                        hops.append(
                            SimulationHop(
                                step=len(hops) + 1,
                                device_id=d_curr.id,
                                device_name=d_curr.name,
                                device_type=d_curr.type.value,
                                out_interface=curr_port,
                                status="dropped",
                                message=(
                                    f"Falla Capa 2: El puerto {curr_port} de {d_curr.name} hacia el Router {d_next.name} "
                                    f"no está en modo trunk y descarta tramas 802.1Q."
                                ),
                            )
                        )
                        return False, f"Puerto troncal requerido en {d_curr.name}:{curr_port} hacia {d_next.name}.", "L2", current_vlan

                    if current_vlan is not None and curr_if.trunk_allowed_vlans is not None and current_vlan not in curr_if.trunk_allowed_vlans:
                        hops.append(
                            SimulationHop(
                                step=len(hops) + 1,
                                device_id=d_curr.id,
                                device_name=d_curr.name,
                                device_type=d_curr.type.value,
                                out_interface=curr_port,
                                status="dropped",
                                message=f"Falla Capa 2: El troncal {curr_port} en {d_curr.name} no permite la VLAN {current_vlan}.",
                            )
                        )
                        return False, f"VLAN {current_vlan} bloqueada en {d_curr.name}:{curr_port}.", "L2", current_vlan

                    # Verificar que el router tenga subinterfaz para current_vlan
                    if current_vlan is not None:
                        matching_sub = next((s for s in subifs if s.encapsulation_dot1q == current_vlan), None)
                        if not matching_sub:
                            hops.append(
                                SimulationHop(
                                    step=len(hops) + 1,
                                    device_id=d_next.id,
                                    device_name=d_next.name,
                                    device_type=d_next.type.value,
                                    in_interface=next_port,
                                    status="dropped",
                                    message=f"Falla Capa 3: {d_next.name} no tiene subinterfaz 'encapsulation dot1Q {current_vlan}' en {next_port}.",
                                )
                            )
                            return False, f"Falta subinterfaz dot1Q {current_vlan} en {d_next.name}.", "L3", current_vlan

            # Router -> Switch (al salir del router hacia la VLAN destino)
            elif d_curr.type == DeviceType.ROUTER and d_next.type == DeviceType.SWITCH:
                base_r_if = _canonical_if_name(curr_port.split(".")[0])
                subifs = [
                    iface for iface in d_curr.interfaces
                    if _canonical_if_name(iface.name).startswith(base_r_if + ".") and iface.encapsulation_dot1q is not None
                ]
                if subifs:
                    if not next_if or next_if.switchport_mode != SwitchportMode.TRUNK:
                        hops.append(
                            SimulationHop(
                                step=len(hops) + 1,
                                device_id=d_next.id,
                                device_name=d_next.name,
                                device_type=d_next.type.value,
                                in_interface=next_port,
                                status="dropped",
                                message=(
                                    f"Falla Capa 2: El puerto {next_port} de {d_next.name} conectado a {d_curr.name} "
                                    f"debe ser troncal (trunk) para recibir tramas 802.1Q."
                                ),
                            )
                        )
                        return False, f"Puerto troncal requerido en {d_next.name}:{next_port}.", "L2", current_vlan

                    # Determinar VLAN de salida según la subinterfaz cuya subred contiene target_ip
                    if target_ip:
                        out_sub = None
                        try:
                            tgt_addr = ipaddress.IPv4Address(target_ip)
                            for s in subifs:
                                if s.ip_address and s.subnet_mask:
                                    sub_net = ipaddress.IPv4Network(f"{s.ip_address}/{s.subnet_mask}", strict=False)
                                    if tgt_addr in sub_net:
                                        out_sub = s
                                        break
                        except ValueError:
                            pass
                        if out_sub:
                            current_vlan = out_sub.encapsulation_dot1q
                            if next_if.trunk_allowed_vlans is not None and current_vlan not in next_if.trunk_allowed_vlans:
                                hops.append(
                                    SimulationHop(
                                        step=len(hops) + 1,
                                        device_id=d_next.id,
                                        device_name=d_next.name,
                                        device_type=d_next.type.value,
                                        in_interface=next_port,
                                        status="dropped",
                                        message=f"Falla Capa 2: El troncal {next_port} en {d_next.name} bloquea la VLAN {current_vlan}.",
                                    )
                                )
                                return False, f"VLAN {current_vlan} bloqueada en {d_next.name}:{next_port}.", "L2", current_vlan

            is_last_hop = is_final_segment and (i == len(path_links_objs) - 1)
            hops.append(
                SimulationHop(
                    step=len(hops) + 1,
                    device_id=d_next.id,
                    device_name=d_next.name,
                    device_type=d_next.type.value,
                    in_interface=next_port,
                    out_interface=None,
                    status="reached" if is_last_hop else "forwarded",
                    message=(
                        f"Trama recibida en {d_next.name} por {next_port}"
                        + (f" (VLAN {current_vlan})." if current_vlan is not None and d_next.type == DeviceType.SWITCH else ".")
                    ),
                )
            )

        return True, None, None, current_vlan

    @staticmethod
    def _bfs_path(topology: Topology, start_id: str, end_id: str) -> Optional[Tuple[List[str], List[Link]]]:
        if start_id == end_id:
            return [start_id], []
        visited = {start_id}
        queue = deque([(start_id, [start_id], [])])

        while queue:
            curr_id, path_d, path_l = queue.popleft()
            for link in topology.links:
                neighbor = None
                if link.source_device == curr_id and link.target_device not in visited:
                    neighbor = link.target_device
                elif link.target_device == curr_id and link.source_device not in visited:
                    neighbor = link.source_device

                if neighbor:
                    new_d = path_d + [neighbor]
                    new_l = path_l + [link]
                    if neighbor == end_id:
                        return new_d, new_l
                    visited.add(neighbor)
                    queue.append((neighbor, new_d, new_l))
        return None

    @staticmethod
    def _find_router_for_ip(topology: Topology, ip_str: str) -> Optional[Device]:
        for dev in topology.devices:
            if dev.type == DeviceType.ROUTER:
                if any(i.ip_address == ip_str for i in dev.interfaces):
                    return dev
        return None

    @staticmethod
    def _get_device_ip_mask(dev: Device):
        for i in dev.interfaces:
            if i.ip_address and i.subnet_mask and i.ip_address != "unassigned":
                return i.ip_address, i.subnet_mask
        return None, None

    @staticmethod
    def _get_first_up_interface(dev: Device):
        for i in dev.interfaces:
            if i.status == InterfaceStatus.UP:
                return i.name
        return dev.interfaces[0].name if dev.interfaces else "Fa0"
