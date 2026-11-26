"""
Reglas de diagnóstico para protocolos de enrutamiento dinámico (OSPF) y servicios DHCP.
Detecta:
1. OSPF Area Mismatch: Dos routers conectados en el mismo segmento con OSPF configurado en áreas diferentes.
2. OSPF Wildcard Mask incorrecta: Uso erróneo de máscaras de subred (ej: 255.255.255.0) en vez de wildcard (0.0.0.255).
3. DHCP Pool con Default Router fuera de subred.
"""

import re
import ipaddress
from typing import List, Dict, Set, Tuple
from app.core.models import Topology, DeviceType, DiagnosticFinding, DiagnosticSeverity


def check_ospf_dhcp_rules(topology: Topology) -> List[DiagnosticFinding]:
    findings: List[DiagnosticFinding] = []

    # 1. Parsear bloques OSPF y DHCP del raw_config de routers y switches
    device_ospf_networks: Dict[str, List[Tuple[ipaddress.IPv4Network, str]]] = {} # dev_id -> [(net, area)]
    device_dhcp_pools: Dict[str, List[Dict[str, str]]] = {} # dev_id -> [{name, network, mask, default_router}]

    for dev in topology.devices:
        if not dev.raw_config:
            continue

        lines = [l.strip() for l in dev.raw_config.splitlines()]
        current_dhcp_pool = None

        for line in lines:
            # OSPF network statement: network 192.168.1.0 0.0.0.255 area 0
            ospf_match = re.match(r"^network\s+([0-9\.]+)\s+([0-9\.]+)\s+area\s+(\w+)", line, re.IGNORECASE)
            if ospf_match:
                net_str = ospf_match.group(1)
                wild_str = ospf_match.group(2)
                area_str = ospf_match.group(3)

                # Detección de Wildcard invertida (usó máscara regular 255.255.255.0 como wildcard)
                if wild_str.startswith("255."):
                    try:
                        suggested_wild = ".".join(str(255 - int(p)) for p in wild_str.split("."))
                    except ValueError:
                        suggested_wild = "0.0.0.255"
                    findings.append(
                        DiagnosticFinding(
                            id=f"ospf_wildcard_inverted_{dev.id}_{net_str.replace('.', '_')}",
                            rule_id="RULE_L3_OSPF_INVERTED_WILDCARD",
                            severity=DiagnosticSeverity.ERROR,
                            layer="L3",
                            device_id=dev.id,
                            device_name=dev.name,
                            title=f"Máscara Wildcard incorrecta en OSPF ({dev.name})",
                            description=(
                                f"En la sentencia 'network {net_str} {wild_str} area {area_str}' de {dev.name}, "
                                f"se configuró una máscara de subred convencional ({wild_str}) en vez de una máscara Wildcard (inversa)."
                            ),
                            hint_level1="Recuerda la regla de OSPF en Cisco IOS: ¿se utiliza la máscara de subred o la máscara Wildcard (inversa)?",
                            hint_level2=f"Para una red con máscara {wild_str}, la máscara inversa Wildcard es {suggested_wild}.",
                            technical_solution=(
                                f"{dev.name}(config-router)# no network {net_str} {wild_str} area {area_str}\n"
                                f"{dev.name}(config-router)# network {net_str} {suggested_wild} area {area_str}"
                            )
                        )
                    )

                # Calcular red normal
                try:
                    # Invertir wildcard para calcular prefijo
                    wild_parts = [int(p) for p in wild_str.split(".")]
                    mask_parts = [255 - p for p in wild_parts]
                    mask_str = ".".join(str(p) for p in mask_parts)
                    net_obj = ipaddress.IPv4Network(f"{net_str}/{mask_str}", strict=False)
                    device_ospf_networks.setdefault(dev.id, []).append((net_obj, area_str))
                except Exception:
                    pass

            # Bloque DHCP: ip dhcp pool ESTUDIANTES (soporta guiones/puntos)
            dhcp_match = re.match(r"^ip\s+dhcp\s+pool\s+(\S+)", line, re.IGNORECASE)
            if dhcp_match:
                if current_dhcp_pool:
                    device_dhcp_pools.setdefault(dev.id, []).append(current_dhcp_pool)
                current_dhcp_pool = {"name": dhcp_match.group(1), "network": "", "mask": "", "default_router": ""}
                continue

            if current_dhcp_pool:
                net_match = re.match(r"^network\s+([0-9\.]+)\s+([0-9\.]+)", line, re.IGNORECASE)
                if net_match:
                    current_dhcp_pool["network"] = net_match.group(1)
                    current_dhcp_pool["mask"] = net_match.group(2)
                
                dr_match = re.match(r"^default-router\s+([0-9\.]+)", line, re.IGNORECASE)
                if dr_match:
                    current_dhcp_pool["default_router"] = dr_match.group(1)

                if line.startswith("!") or line.startswith("interface") or line.startswith("ip dhcp"):
                    device_dhcp_pools.setdefault(dev.id, []).append(current_dhcp_pool)
                    current_dhcp_pool = None

        if current_dhcp_pool:
            device_dhcp_pools.setdefault(dev.id, []).append(current_dhcp_pool)

    # 2. Validar DHCP Pools
    for dev in topology.devices:
        pools = device_dhcp_pools.get(dev.id, [])
        for pool in pools:
            if pool.get("network") and pool.get("mask") and pool.get("default_router"):
                try:
                    pool_net = ipaddress.IPv4Network(f"{pool['network']}/{pool['mask']}", strict=False)
                    dr_ip = ipaddress.IPv4Address(pool["default_router"])
                    if dr_ip not in pool_net:
                        findings.append(
                            DiagnosticFinding(
                                id=f"dhcp_dr_out_of_subnet_{dev.id}_{pool['name']}",
                                rule_id="RULE_L3_DHCP_DEFAULT_ROUTER_OUT_OF_SUBNET",
                                severity=DiagnosticSeverity.ERROR,
                                layer="L3",
                                device_id=dev.id,
                                device_name=dev.name,
                                title=f"Default-Router fuera de subred en pool DHCP '{pool['name']}'",
                                description=(
                                    f"En el servidor DHCP {dev.name}, el pool '{pool['name']}' reparte la red {pool_net}, "
                                    f"pero su default-router ({pool['default_router']}) no pertenece a esa subred."
                                ),
                                hint_level1="Los clientes que reciban IP por DHCP no podrán salir de su red local si la puerta de enlace está fuera de su segmento.",
                                hint_level2=f"Verifica la subred {pool_net} del pool '{pool['name']}' y asigna un default-router dentro del mismo rango.",
                                technical_solution=(
                                    f"{dev.name}(config)# ip dhcp pool {pool['name']}\n"
                                    f"{dev.name}(dhcp-config)# default-router <IP_EN_SUBRED_{pool_net.network_address}>"
                                )
                            )
                        )
                except ValueError:
                    pass

    # 3. OSPF Area Mismatch en enlaces conectados
    device_map = {d.id: d for d in topology.devices}
    for link in topology.links:
        dev1 = device_map.get(link.source_device)
        dev2 = device_map.get(link.target_device)
        if not dev1 or not dev2:
            continue

        ospf1 = device_ospf_networks.get(dev1.id, [])
        ospf2 = device_ospf_networks.get(dev2.id, [])
        if not ospf1 or not ospf2:
            continue

        if1 = next((i for i in dev1.interfaces if i.name == link.source_interface), None)
        if2 = next((i for i in dev2.interfaces if i.name == link.target_interface), None)

        if if1 and if2 and if1.ip_address and if2.ip_address:
            try:
                ip1 = ipaddress.IPv4Address(if1.ip_address)
                ip2 = ipaddress.IPv4Address(if2.ip_address)

                area1 = next((area for net, area in ospf1 if ip1 in net), None)
                area2 = next((area for net, area in ospf2 if ip2 in net), None)

                if area1 is not None and area2 is not None and area1 != area2:
                    findings.append(
                        DiagnosticFinding(
                            id=f"ospf_area_mismatch_{dev1.id}_{dev2.id}",
                            rule_id="RULE_L3_OSPF_AREA_MISMATCH",
                            severity=DiagnosticSeverity.ERROR,
                            layer="L3",
                            device_id=dev1.id,
                            device_name=dev1.name,
                            related_device_id=dev2.id,
                            title=f"Discrepancia de Área OSPF entre {dev1.name} y {dev2.name}",
                            description=(
                                f"El enlace directo entre {dev1.name} ({if1.name}) y {dev2.name} ({if2.name}) tiene "
                                f"un conflicto de adyacencia OSPF: {dev1.name} está en el Área {area1} y {dev2.name} en el Área {area2}. "
                                f"No formarán relación de vecindad."
                            ),
                            hint_level1="Para que dos routers formen adyacencia OSPF en un mismo enlace, ¿qué parámetro de área deben compartir obligatoriamente?",
                            hint_level2=f"Compara el área OSPF de {dev1.name} (Área {area1}) con la de {dev2.name} (Área {area2}). Deben ser idénticas.",
                            technical_solution=(
                                f"Homologa el área en ambos extremos del enlace:\n\n"
                                f"{dev2.name}(config-router)# network <IP_RED> <WILDCARD> area {area1}"
                            )
                        )
                    )
            except ValueError:
                pass

    return findings

