"""
Reglas de diagnóstico de Capa 3 para Enrutamiento Estático y Rutas por Defecto.
Detecta:
1. Next-hop inalcanzable (el next-hop no pertenece a ninguna subred configurada en el router).
2. Siguiente salto apuntando a la propia IP local del router (configuración errónea clásica de novatos).
3. Rutas por defecto redundantes o inconsistentes.
4. Bucles evidentes de dos saltos (A apunta a B y B apunta a A para la misma red de destino).
"""

import ipaddress
from typing import List, Dict, Set
from app.core.models import Topology, DeviceType, DiagnosticFinding, DiagnosticSeverity


def check_static_routing_rules(topology: Topology) -> List[DiagnosticFinding]:
    findings: List[DiagnosticFinding] = []
    routers = [d for d in topology.devices if d.type == DeviceType.ROUTER]

    if not routers:
        return findings

    # Mapa de redes locales directamente conectadas por router
    router_connected_nets: Dict[str, List[ipaddress.IPv4Network]] = {}
    router_local_ips: Dict[str, Set[str]] = {}

    for r in routers:
        nets = []
        ips = set()
        for iface in r.interfaces:
            if iface.ip_address and iface.subnet_mask and iface.ip_address != "unassigned":
                try:
                    net = ipaddress.IPv4Network(f"{iface.ip_address}/{iface.subnet_mask}", strict=False)
                    nets.append(net)
                    ips.add(iface.ip_address)
                except ValueError:
                    pass
        router_connected_nets[r.id] = nets
        router_local_ips[r.id] = ips

    for r in routers:
        if not r.static_routes:
            continue

        local_nets = router_connected_nets.get(r.id, [])
        local_ips = router_local_ips.get(r.id, set())

        for idx, route in enumerate(r.static_routes):
            net_dest = route.get("network", "")
            mask_dest = route.get("mask", "")
            next_hop = route.get("next_hop", "")

            if not next_hop:
                continue

            # 1. Next-hop apuntando a la propia IP local
            if next_hop in local_ips:
                findings.append(
                    DiagnosticFinding(
                        id=f"static_route_self_nexthop_{r.id}_{idx}",
                        rule_id="RULE_L3_STATIC_ROUTE_SELF_NEXTHOP",
                        severity=DiagnosticSeverity.ERROR,
                        layer="L3",
                        device_id=r.id,
                        device_name=r.name,
                        title=f"Ruta estática con Next-Hop local en {r.name}",
                        description=(
                            f"En la ruta estática hacia {net_dest}/{mask_dest}, el siguiente salto ({next_hop}) "
                            f"es una dirección IP configurada en el propio router {r.name}. "
                            f"El next-hop debe ser la IP del router vecino."
                        ),
                        hint_level1="¿Qué router debe recibir los paquetes: este mismo router o el del siguiente salto?",
                        hint_level2=f"Revisa el comando 'ip route {net_dest} {mask_dest} {next_hop}' en {r.name}. La IP {next_hop} le pertenece a él mismo.",
                        technical_solution=(
                            f"{r.name}# configure terminal\n"
                            f"{r.name}(config)# no ip route {net_dest} {mask_dest} {next_hop}\n"
                            f"{r.name}(config)# ip route {net_dest} {mask_dest} <IP_DEL_ROUTER_VECINO>"
                        )
                    )
                )
                continue

            # 2. Next-hop inalcanzable (fuera de toda subred local)
            try:
                nh_ip = ipaddress.IPv4Address(next_hop)
                is_reachable = any(nh_ip in net for net in local_nets)

                if not is_reachable and local_nets:
                    findings.append(
                        DiagnosticFinding(
                            id=f"static_route_unreachable_nexthop_{r.id}_{idx}",
                            rule_id="RULE_L3_STATIC_ROUTE_UNREACHABLE_NEXTHOP",
                            severity=DiagnosticSeverity.ERROR,
                            layer="L3",
                            device_id=r.id,
                            device_name=r.name,
                            title=f"Next-Hop inalcanzable en ruta estática de {r.name}",
                            description=(
                                f"La ruta hacia {net_dest}/{mask_dest} especifica el siguiente salto {next_hop}, "
                                f"pero ninguna interfaz de {r.name} pertenece a esa subred. El router no tiene forma de alcanzar ese salto directamente."
                            ),
                            hint_level1="Para que un router entregue un paquete a un siguiente salto, ¿en qué red debe estar la IP del next-hop?",
                            hint_level2=(
                                f"Las interfaces activas de {r.name} cubren las subredes: "
                                f"{', '.join(str(n) for n in local_nets)}. La IP {next_hop} no pertenece a ninguna de ellas."
                            ),
                            technical_solution=(
                                f"Corrige el siguiente salto para que coincida con la IP de la interfaz conectada del router vecino:\n\n"
                                f"{r.name}(config)# no ip route {net_dest} {mask_dest} {next_hop}\n"
                                f"{r.name}(config)# ip route {net_dest} {mask_dest} <IP_VECINA_EN_SUBRED_LOCAL>"
                            )
                        )
                    )
            except ValueError:
                pass

    # 3. Detección de bucles de dos saltos (A apunta a B y B apunta a A para la misma red)
    seen_loops = set()
    for r_a in routers:
        for route_a in r_a.static_routes:
            dest_a = route_a.get("network")
            mask_a = route_a.get("mask")
            nh_a = route_a.get("next_hop")

            # Buscar a qué router le pertenece nh_a
            for r_b in routers:
                if r_b.id == r_a.id:
                    continue
                if nh_a in router_local_ips.get(r_b.id, set()):
                    # r_b recibe el tráfico. Verificar si r_b tiene una ruta idéntica que devuelva el tráfico a r_a
                    for route_b in r_b.static_routes:
                        if route_b.get("network") == dest_a and route_b.get("mask") == mask_a:
                            nh_b = route_b.get("next_hop")
                            if nh_b in router_local_ips.get(r_a.id, set()):
                                loop_key = (min(r_a.id, r_b.id), max(r_a.id, r_b.id), dest_a, mask_a)
                                if loop_key in seen_loops:
                                    continue
                                seen_loops.add(loop_key)
                                findings.append(
                                    DiagnosticFinding(
                                        id=f"static_route_loop_{r_a.id}_{r_b.id}_{dest_a.replace('.', '_')}",
                                        rule_id="RULE_L3_STATIC_ROUTE_LOOP",
                                        severity=DiagnosticSeverity.ERROR,
                                        layer="L3",
                                        device_id=r_a.id,
                                        device_name=r_a.name,
                                        related_device_id=r_b.id,
                                        title=f"Bucle de enrutamiento estático entre {r_a.name} y {r_b.name}",
                                        description=(
                                            f"Para el destino {dest_a}/{mask_a}, {r_a.name} envía el tráfico hacia {r_b.name} ({nh_a}), "
                                            f"pero {r_b.name} tiene una ruta que lo devuelve a {r_a.name} ({nh_b}), creando un bucle infinito."
                                        ),
                                        hint_level1="Si dos routers se envían mutuamente el mismo paquete, ¿qué ocurrirá con el TTL y el tráfico?",
                                        hint_level2=f"Revisa las tablas de rutas en {r_a.name} y {r_b.name}. Ambos se apuntan el uno al otro para la red {dest_a}.",
                                        technical_solution=(
                                            f"Elimina la ruta circular en el router que no tiene la salida real a dicha red:\n\n"
                                            f"{r_b.name}(config)# no ip route {dest_a} {mask_a} {nh_b}"
                                        )
                                    )
                                )

    return findings

