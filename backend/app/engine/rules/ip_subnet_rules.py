import ipaddress
from typing import List, Dict, Set
from app.core.models import Topology, DeviceType, DiagnosticFinding, DiagnosticSeverity

def check_ip_subnet_rules(topology: Topology) -> List[DiagnosticFinding]:
    """
    Verifica reglas de Capa 3: subredes coincidentes en enlaces punto a punto,
    duplicados de IP, y máscaras válidas.
    """
    findings: List[DiagnosticFinding] = []
    device_map = {d.id: d for d in topology.devices}

    # 1. Detección de IPs duplicadas en toda la topología
    ip_occurrences: Dict[str, List[tuple]] = {}
    for dev in topology.devices:
        for iface in dev.interfaces:
            if iface.ip_address and iface.ip_address != "unassigned":
                ip_occurrences.setdefault(iface.ip_address, []).append((dev, iface))

    for ip_addr, occurrences in ip_occurrences.items():
        if len(occurrences) > 1:
            dev_names = [f"{dev.name} ({iface.name})" for dev, iface in occurrences]
            primary_dev, primary_if = occurrences[0]
            findings.append(
                DiagnosticFinding(
                    id=f"ip_dup_{ip_addr.replace('.', '_')}",
                    rule_id="RULE_L3_DUPLICATE_IP",
                    severity=DiagnosticSeverity.ERROR,
                    layer="L3",
                    device_id=primary_dev.id,
                    device_name=primary_dev.name,
                    interface_name=primary_if.name,
                    title=f"Dirección IP duplicada detectada ({ip_addr})",
                    description=f"La dirección IP {ip_addr} está configurada en múltiples equipos: {', '.join(dev_names)}.",
                    hint_level1="Recuerda el principio básico de direccionamiento IP: ¿pueden dos interfaces compartir la misma dirección lógica en una red?",
                    hint_level2=f"Revisa los equipos {dev_names[0]} y {dev_names[1]}. Ambos reclaman la IP {ip_addr}.",
                    technical_solution=f"Asigna una IP única del rango correspondiente a cada equipo para evitar conflictos ARP."
                )
            )

    # 2. Subredes en enlaces directos (Router <-> Router o Router <-> Host)
    for link in topology.links:
        dev1 = device_map.get(link.source_device)
        dev2 = device_map.get(link.target_device)
        if not dev1 or not dev2:
            continue

        if1 = next((i for i in dev1.interfaces if i.name == link.source_interface), None)
        if2 = next((i for i in dev2.interfaces if i.name == link.target_interface), None)

        if if1 and if2 and if1.ip_address and if2.ip_address and if1.subnet_mask and if2.subnet_mask:
            try:
                net1 = ipaddress.IPv4Network(f"{if1.ip_address}/{if1.subnet_mask}", strict=False)
                net2 = ipaddress.IPv4Network(f"{if2.ip_address}/{if2.subnet_mask}", strict=False)

                if net1 != net2:
                    findings.append(
                        DiagnosticFinding(
                            id=f"subnet_mismatch_{dev1.id}_{if1.name}",
                            rule_id="RULE_L3_SUBNET_MISMATCH_DIRECT_LINK",
                            severity=DiagnosticSeverity.ERROR,
                            layer="L3",
                            device_id=dev1.id,
                            device_name=dev1.name,
                            interface_name=if1.name,
                            related_device_id=dev2.id,
                            related_interface_name=if2.name,
                            title="Desajuste de Subred en Enlace Directo",
                            description=(
                                f"Los extremos del enlace entre {dev1.name} ({if1.name}: {if1.ip_address}/{if1.subnet_mask}) "
                                f"y {dev2.name} ({if2.name}: {if2.ip_address}/{if2.subnet_mask}) pertenecen a diferentes subredes "
                                f"({net1.network_address} vs {net2.network_address})."
                            ),
                            hint_level1="Para que dos interfaces conectadas por un mismo cable directo se comuniquen en Capa 3, ¿qué deben tener en común sus direcciones IP?",
                            hint_level2=f"Revisa las máscaras y direcciones en {dev1.name} ({if1.name}) y {dev2.name} ({if2.name}). No están dentro de la misma subred de difusión.",
                            technical_solution=(
                                f"Configura ambas interfaces en la misma subred (por ejemplo en {net1}):\n\n"
                                f"{dev2.name}(config)# interface {if2.name}\n"
                                f"{dev2.name}(config-if)# ip address <IP_EN_RED_{net1.network_address}> {if1.subnet_mask}"
                            )
                        )
                    )
            except ValueError:
                pass

    # 3. Solapamiento de subredes entre distintas VLANs (hosts en diferentes VLANs usando la misma subred IP)
    vlan_subnets: Dict[int, Set[ipaddress.IPv4Network]] = {}
    vlan_sample_host: Dict[int, tuple] = {}

    for link in topology.links:
        dev1 = device_map.get(link.source_device)
        dev2 = device_map.get(link.target_device)
        if not dev1 or not dev2:
            continue

        host, sw, sw_port = None, None, None
        if dev1.type in (DeviceType.PC, DeviceType.SERVER) and dev2.type == DeviceType.SWITCH:
            host, sw, sw_port = dev1, dev2, link.target_interface
        elif dev2.type in (DeviceType.PC, DeviceType.SERVER) and dev1.type == DeviceType.SWITCH:
            host, sw, sw_port = dev2, dev1, link.source_interface

        if host and sw:
            sw_if = next((i for i in sw.interfaces if i.name == sw_port), None)
            host_if = next((i for i in host.interfaces if i.ip_address and i.subnet_mask), None)
            if sw_if and host_if:
                vlan_id = sw_if.access_vlan or 1
                try:
                    net = ipaddress.IPv4Network(f"{host_if.ip_address}/{host_if.subnet_mask}", strict=False)
                    vlan_subnets.setdefault(vlan_id, set()).add(net)
                    vlan_sample_host.setdefault(vlan_id, (host, host_if, sw, sw_if))
                except ValueError:
                    pass

    checked_pairs = set()
    for v1, nets1 in vlan_subnets.items():
        for v2, nets2 in vlan_subnets.items():
            if v1 >= v2 or (v1, v2) in checked_pairs:
                continue
            checked_pairs.add((v1, v2))
            shared_nets = nets1 & nets2
            for shared_net in shared_nets:
                h1, hif1, sw1, swif1 = vlan_sample_host[v1]
                h2, hif2, sw2, swif2 = vlan_sample_host[v2]
                block_size = shared_net.num_addresses
                findings.append(
                    DiagnosticFinding(
                        id=f"vlan_subnet_overlap_{v1}_{v2}_{str(shared_net.network_address).replace('.', '_')}",
                        rule_id="RULE_L3_VLAN_SUBNET_OVERLAP",
                        severity=DiagnosticSeverity.ERROR,
                        layer="L3",
                        device_id=sw1.id,
                        device_name=sw1.name,
                        interface_name=swif1.name,
                        related_device_id=h2.id,
                        title=f"Solapamiento de Subred {shared_net} entre VLAN {v1} y VLAN {v2}",
                        description=(
                            f"Equipos en distintas VLANs (VLAN {v1}, ej. {h1.name}: {hif1.ip_address} y "
                            f"VLAN {v2}, ej. {h2.name}: {hif2.ip_address}) pertenecen a la misma subred lógica "
                            f"{shared_net} (rango {shared_net.network_address} - {shared_net.broadcast_address}, bloque de {block_size} IPs)."
                        ),
                        hint_level1=(
                            f"En diseño de redes con VLSM/Subredes, ¿pueden dos VLANs distintas compartir la misma subred IP ({shared_net})? "
                            f"Con máscara {hif1.subnet_mask} (/{shared_net.prefixlen}), ¿de cuánto en cuánto avanzan los bloques de subred?"
                        ),
                        hint_level2=(
                            f"Observa la máscara {hif1.subnet_mask} (/{shared_net.prefixlen}): cada subred abarca {block_size} direcciones "
                            f"(desde {shared_net.network_address} hasta {shared_net.broadcast_address}). Tanto {h1.name} (VLAN {v1}) "
                            f"como {h2.name} (VLAN {v2}) cayeron dentro del mismo bloque {shared_net}."
                        ),
                        technical_solution=(
                            f"Asigna una subred /{shared_net.prefixlen} diferente a cada VLAN (avanzando de {block_size} en {block_size}) "
                            f"o ajusta la máscara de subred (por ejemplo a /28 = 255.255.255.240 si querías bloques de 16 IPs)."
                        )
                    )
                )

    return findings
