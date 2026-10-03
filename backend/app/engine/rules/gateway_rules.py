import ipaddress
from typing import List, Set
from app.core.models import Topology, DeviceType, DiagnosticFinding, DiagnosticSeverity

def check_gateway_rules(topology: Topology) -> List[DiagnosticFinding]:
    """
    Verifica que los hosts (PCs, servidores, switches) tengan una puerta de enlace (Default Gateway)
    válida, dentro de su misma subred y existente en un router de la topología.
    """
    findings: List[DiagnosticFinding] = []

    # Recolectar todas las IPs de routers activas en la topología
    router_ips: Set[str] = set()
    for dev in topology.devices:
        if dev.type == DeviceType.ROUTER:
            for iface in dev.interfaces:
                if iface.ip_address and iface.ip_address != "unassigned":
                    router_ips.add(iface.ip_address)

    for dev in topology.devices:
        if dev.type in [DeviceType.PC, DeviceType.SERVER]:
            # Obtener la interfaz principal del host
            main_if = next((i for i in dev.interfaces if i.ip_address), None)
            if not main_if or not main_if.ip_address:
                findings.append(
                    DiagnosticFinding(
                        id=f"host_no_ip_{dev.id}",
                        rule_id="RULE_L3_HOST_UNCONFIGURED_IP",
                        severity=DiagnosticSeverity.ERROR,
                        layer="L3",
                        device_id=dev.id,
                        device_name=dev.name,
                        title=f"{dev.name} no tiene dirección IP asignada",
                        description=f"El equipo final {dev.name} carece de dirección IP configurada.",
                        hint_level1="Un dispositivo final no puede comunicarse en la red sin una identidad de Capa 3.",
                        hint_level2=f"Abre la configuración IP de {dev.name} y establece una dirección estática o habilita DHCP.",
                        technical_solution=f"Asigna IP, máscara y default gateway en {dev.name}."
                    )
                )
                continue

            # Verificar si falta el gateway
            if not dev.default_gateway:
                findings.append(
                    DiagnosticFinding(
                        id=f"gw_missing_{dev.id}",
                        rule_id="RULE_L3_MISSING_DEFAULT_GATEWAY",
                        severity=DiagnosticSeverity.WARNING,
                        layer="L3",
                        device_id=dev.id,
                        device_name=dev.name,
                        interface_name=main_if.name,
                        title=f"Puerta de enlace ausente en {dev.name}",
                        description=f"{dev.name} tiene IP ({main_if.ip_address}) pero no tiene configurado un Default Gateway.",
                        hint_level1="¿Qué necesita un host para enviar paquetes a dispositivos que están fuera de su propia red local?",
                        hint_level2=f"Revisa la casilla 'Default Gateway' en la configuración de {dev.name}.",
                        technical_solution="Configura la IP del router más cercano (interfaz local o subinterfaz de su VLAN) como Default Gateway."
                    )
                )
                continue

            # Verificar si el default gateway está en la misma subred del host
            if main_if.subnet_mask:
                try:
                    host_net = ipaddress.IPv4Network(f"{main_if.ip_address}/{main_if.subnet_mask}", strict=False)
                    gw_ip = ipaddress.IPv4Address(dev.default_gateway)

                    if gw_ip not in host_net:
                        findings.append(
                            DiagnosticFinding(
                                id=f"gw_out_of_subnet_{dev.id}",
                                rule_id="RULE_L3_GATEWAY_OUT_OF_SUBNET",
                                severity=DiagnosticSeverity.ERROR,
                                layer="L3",
                                device_id=dev.id,
                                device_name=dev.name,
                                interface_name=main_if.name,
                                title=f"Default Gateway fuera de subred en {dev.name}",
                                description=(
                                    f"La puerta de enlace {dev.default_gateway} configurada en {dev.name} "
                                    f"no pertenece a su subred local ({host_net})."
                                ),
                                hint_level1="¿Puede un host enviar paquetes directamente a un gateway que pertenece a una red distinta sin pasar por un router?",
                                hint_level2=(
                                    f"La IP de {dev.name} es {main_if.ip_address} con máscara {main_if.subnet_mask} (red {host_net.network_address}). "
                                    f"Sin embargo, el gateway apunta a {dev.default_gateway}."
                                ),
                                technical_solution=f"Cambia el Default Gateway de {dev.name} por la IP del router en la subred {host_net}."
                            )
                        )
                    elif router_ips and dev.default_gateway not in router_ips:
                        findings.append(
                            DiagnosticFinding(
                                id=f"gw_unreachable_ip_{dev.id}",
                                rule_id="RULE_L3_GATEWAY_NONEXISTENT_ON_ROUTER",
                                severity=DiagnosticSeverity.WARNING,
                                layer="L3",
                                device_id=dev.id,
                                device_name=dev.name,
                                interface_name=main_if.name,
                                title=f"El Default Gateway de {dev.name} no coincide con ningún router",
                                description=(
                                    f"El gateway {dev.default_gateway} está en la subred correcta, pero ningún router de la "
                                    f"topología tiene esa dirección IP configurada."
                                ),
                                hint_level1="Verifica qué dirección IP tiene asignada la interfaz del router que atiende esta red.",
                                hint_level2=f"Revisa las interfaces y subinterfaces de los routers. ¿Cuál tiene la IP {dev.default_gateway}?",
                                technical_solution=f"Asegúrate de que la interfaz/subinterfaz del router tenga exactamente la IP {dev.default_gateway}."
                            )
                        )
                except ValueError:
                    pass

    return findings
