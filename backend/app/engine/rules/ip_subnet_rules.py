import ipaddress
from typing import List, Dict
from app.core.models import Topology, DiagnosticFinding, DiagnosticSeverity

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

    return findings
