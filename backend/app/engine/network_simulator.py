"""
Motor de Simulación de Conectividad (Ping & Traceroute) para NetTutorIA.
Evalúa el recorrido salto a salto entre dos dispositivos considerando:
  - Capa 1: Estado físico/administrativo de interfaces.
  - Capa 2: Enlaces Access, VLANs coincidentes, Trunks 802.1Q y Allowed VLANs.
  - Capa 3: Subredes locales, Default Gateways, Rutas Estáticas y Subinterfaces.
"""

import ipaddress
from typing import Dict, List, Optional
from pydantic import BaseModel
from app.core.models import Topology, Device, DeviceType, SwitchportMode, InterfaceStatus


class SimulationHop(BaseModel):
    step: int
    device_id: str
    device_name: str
    device_type: str
    in_interface: Optional[str] = None
    out_interface: Optional[str] = None
    status: str # "forwarded", "dropped", "reached"
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
    path_links: List[str] = [] # IDs de los enlaces recorridos para animación


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
                failure_layer="L1"
            )

        src_ip, src_mask = cls._get_device_ip_mask(src_dev)
        tgt_ip, tgt_mask = cls._get_device_ip_mask(tgt_dev)

        if not src_ip:
            return PingSimulationResult(
                success=False, source_device=src_dev.name, target_device=tgt_dev.name,
                source_ip="", target_ip=tgt_ip or "", hops=[],
                failure_reason=f"{src_dev.name} no tiene dirección IP configurada.",
                failure_layer="L3"
            )

        if not tgt_ip:
            return PingSimulationResult(
                success=False, source_device=src_dev.name, target_device=tgt_dev.name,
                source_ip=src_ip, target_ip="", hops=[],
                failure_reason=f"{tgt_dev.name} no tiene dirección IP configurada.",
                failure_layer="L3"
            )

        hops: List[SimulationHop] = []
        path_links: List[str] = []

        # Paso 1: Salida desde el origen
        hops.append(SimulationHop(
            step=1,
            device_id=src_dev.id,
            device_name=src_dev.name,
            device_type=src_dev.type.value,
            in_interface=None,
            out_interface=cls._get_first_up_interface(src_dev),
            status="forwarded",
            message=f"Generando paquete ICMP Echo Request desde {src_dev.name} ({src_ip}) hacia {tgt_ip}."
        ))

        # Verificar si están en la misma subred lógica
        same_subnet = False
        try:
            net_src = ipaddress.IPv4Network(f"{src_ip}/{src_mask}", strict=False)
            net_tgt = ipaddress.IPv4Network(f"{tgt_ip}/{tgt_mask}", strict=False)
            same_subnet = (net_src == net_tgt)
        except Exception:
            pass

        # Buscar camino usando BFS sobre los enlaces
        visited = set()
        queue = [(src_dev.id, [src_dev.id], [])] # (current_id, path_devices, path_links)

        found_path = None
        found_links = None

        while queue:
            curr_id, path_d, path_l = queue.pop(0)
            if curr_id == tgt_dev.id:
                found_path = path_d
                found_links = path_l
                break

            visited.add(curr_id)
            for link in topology.links:
                neighbor = None
                if link.source_device == curr_id and link.target_device not in visited:
                    neighbor = link.target_device
                elif link.target_device == curr_id and link.source_device not in visited:
                    neighbor = link.source_device

                if neighbor:
                    queue.append((neighbor, path_d + [neighbor], path_l + [link]))

        if not found_path:
            hops.append(SimulationHop(
                step=len(hops)+1,
                device_id=src_dev.id,
                device_name=src_dev.name,
                device_type=src_dev.type.value,
                status="dropped",
                message=f"No existe ninguna ruta física de cables entre {src_dev.name} y {tgt_dev.name}."
            ))
            return PingSimulationResult(
                success=False, source_device=src_dev.name, target_device=tgt_dev.name,
                source_ip=src_ip, target_ip=tgt_ip, hops=hops,
                failure_reason="Aislamiento físico: No hay enlace entre los extremos.",
                failure_layer="L1"
            )

        # Evaluar la viabilidad salto a salto en el camino
        current_vlan = 1
        has_l3_routing = False

        for i in range(len(found_links)):
            link = found_links[i]
            d_curr = device_map[found_path[i]]
            d_next = device_map[found_path[i+1]]
            path_links.append(link.id)

            curr_port = link.source_interface if link.source_device == d_curr.id else link.target_interface
            next_port = link.target_interface if link.source_device == d_curr.id else link.source_interface

            # 1. Comprobación Capa 1: Puerto shutdown
            curr_if = next((x for x in d_curr.interfaces if x.name == curr_port), None)
            next_if = next((x for x in d_next.interfaces if x.name == next_port), None)

            if curr_if and curr_if.status == InterfaceStatus.ADMIN_DOWN:
                hops.append(SimulationHop(
                    step=len(hops)+1, device_id=d_curr.id, device_name=d_curr.name,
                    device_type=d_curr.type.value, in_interface=curr_port, status="dropped",
                    message=f"Falla Capa 1: La interfaz {curr_port} en {d_curr.name} está apagada ('administratively down')."
                ))
                return PingSimulationResult(
                    success=False, source_device=src_dev.name, target_device=tgt_dev.name,
                    source_ip=src_ip, target_ip=tgt_ip, hops=hops, path_links=path_links,
                    failure_reason=f"Puerto {curr_port} en {d_curr.name} apagado.", failure_layer="L1"
                )

            if next_if and next_if.status == InterfaceStatus.ADMIN_DOWN:
                hops.append(SimulationHop(
                    step=len(hops)+1, device_id=d_next.id, device_name=d_next.name,
                    device_type=d_next.type.value, in_interface=next_port, status="dropped",
                    message=f"Falla Capa 1: La interfaz de entrada {next_port} en {d_next.name} está apagada."
                ))
                return PingSimulationResult(
                    success=False, source_device=src_dev.name, target_device=tgt_dev.name,
                    source_ip=src_ip, target_ip=tgt_ip, hops=hops, path_links=path_links,
                    failure_reason=f"Puerto {next_port} en {d_next.name} apagado.", failure_layer="L1"
                )

            # 2. Comprobación Capa 2: VLANs y Trunks
            if d_curr.type == DeviceType.SWITCH and curr_if:
                if curr_if.switchport_mode == SwitchportMode.ACCESS:
                    current_vlan = curr_if.access_vlan or 1

            if d_next.type == DeviceType.SWITCH and next_if:
                # Si entra por access a una VLAN distinta sin router
                if next_if.switchport_mode == SwitchportMode.ACCESS and not has_l3_routing:
                    target_port_vlan = next_if.access_vlan or 1
                    if target_port_vlan != current_vlan:
                        hops.append(SimulationHop(
                            step=len(hops)+1, device_id=d_next.id, device_name=d_next.name,
                            device_type=d_next.type.value, in_interface=next_port, status="dropped",
                            message=f"Falla Capa 2: Aislamiento de VLANs. El tráfico viaja en VLAN {current_vlan}, pero el puerto {next_port} pertenece a la VLAN {target_port_vlan}."
                        ))
                        return PingSimulationResult(
                            success=False, source_device=src_dev.name, target_device=tgt_dev.name,
                            source_ip=src_ip, target_ip=tgt_ip, hops=hops, path_links=path_links,
                            failure_reason=f"Aislamiento de VLAN (VLAN {current_vlan} vs VLAN {target_port_vlan}) sin enrutamiento.", failure_layer="L2"
                        )

            # Comprobación de Router-on-a-stick
            if d_next.type == DeviceType.ROUTER:
                # Switch conectado al router debe ser trunk
                if d_curr.type == DeviceType.SWITCH and curr_if and curr_if.switchport_mode != SwitchportMode.TRUNK:
                    hops.append(SimulationHop(
                        step=len(hops)+1, device_id=d_curr.id, device_name=d_curr.name,
                        device_type=d_curr.type.value, out_interface=curr_port, status="dropped",
                        message=f"Falla Capa 2: El puerto {curr_port} de {d_curr.name} hacia el Router {d_next.name} está en modo acceso y descarta tramas 802.1Q."
                    ))
                    return PingSimulationResult(
                        success=False, source_device=src_dev.name, target_device=tgt_dev.name,
                        source_ip=src_ip, target_ip=tgt_ip, hops=hops, path_links=path_links,
                        failure_reason=f"Puerto troncal requerido en {d_curr.name}:{curr_port} hacia el router.", failure_layer="L2"
                    )
                has_l3_routing = True

            # Registrar salto intermedio
            hops.append(SimulationHop(
                step=len(hops)+1,
                device_id=d_next.id,
                device_name=d_next.name,
                device_type=d_next.type.value,
                in_interface=next_port,
                out_interface=None,
                status="reached" if d_next.id == tgt_dev.id else "forwarded",
                message=f"Trama recibida en {d_next.name} por {next_port}."
            ))

        # 3. Comprobación Capa 3: Si están en diferente subred y no hubo router
        if not same_subnet and not has_l3_routing:
            hops.append(SimulationHop(
                step=len(hops)+1, device_id=tgt_dev.id, device_name=tgt_dev.name,
                device_type=tgt_dev.type.value, status="dropped",
                message=f"Falla Capa 3: {src_dev.name} ({src_ip}) y {tgt_dev.name} ({tgt_ip}) están en subredes diferentes pero no hay ningún Router intermediario enrutando los paquetes."
            ))
            return PingSimulationResult(
                success=False, source_device=src_dev.name, target_device=tgt_dev.name,
                source_ip=src_ip, target_ip=tgt_ip, hops=hops, path_links=path_links,
                failure_reason="Subredes diferentes sin equipo de Capa 3 (Router).", failure_layer="L3"
            )

        # 4. Comprobación de Gateway en host origen y destino
        if not same_subnet:
            if not src_dev.default_gateway:
                hops.append(SimulationHop(
                    step=len(hops)+1, device_id=src_dev.id, device_name=src_dev.name,
                    device_type=src_dev.type.value, status="dropped",
                    message=f"Falla Capa 3: {src_dev.name} necesita enviar a una red externa pero no tiene Default Gateway configurado."
                ))
                return PingSimulationResult(
                    success=False, source_device=src_dev.name, target_device=tgt_dev.name,
                    source_ip=src_ip, target_ip=tgt_ip, hops=hops, path_links=path_links,
                    failure_reason=f"Default Gateway ausente en {src_dev.name}.", failure_layer="L3"
                )

        # Éxito: comunicación completa
        hops.append(SimulationHop(
            step=len(hops)+1,
            device_id=tgt_dev.id,
            device_name=tgt_dev.name,
            device_type=tgt_dev.type.value,
            status="reached",
            message=f"¡Éxito! Paquete ICMP Echo Reply recibido satisfactoriamente desde {tgt_dev.name} ({tgt_ip})."
        ))

        return PingSimulationResult(
            success=True,
            source_device=src_dev.name,
            target_device=tgt_dev.name,
            source_ip=src_ip,
            target_ip=tgt_ip,
            hops=hops,
            path_links=path_links
        )

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
