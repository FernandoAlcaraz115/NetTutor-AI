from typing import List
from app.core.models import Topology, InterfaceStatus, DiagnosticFinding, DiagnosticSeverity

def check_interface_status_rules(topology: Topology) -> List[DiagnosticFinding]:
    """
    Verifica estado físico/administrativo de las interfaces conectadas (missing 'no shutdown').
    """
    findings: List[DiagnosticFinding] = []
    device_map = {d.id: d for d in topology.devices}

    # 1. Enlaces conectados con puertos administrativamente apagados
    for link in topology.links:
        dev1 = device_map.get(link.source_device)
        dev2 = device_map.get(link.target_device)
        if not dev1 or not dev2:
            continue

        if1 = next((i for i in dev1.interfaces if i.name == link.source_interface), None)
        if2 = next((i for i in dev2.interfaces if i.name == link.target_interface), None)

        for dev, iface, other_dev in [(dev1, if1, dev2), (dev2, if2, dev1)]:
            if iface and iface.status == InterfaceStatus.ADMIN_DOWN:
                findings.append(
                    DiagnosticFinding(
                        id=f"if_admin_down_{dev.id}_{iface.name.replace('/', '_')}",
                        rule_id="RULE_L1_INTERFACE_ADMIN_DOWN",
                        severity=DiagnosticSeverity.ERROR,
                        layer="L1",
                        device_id=dev.id,
                        device_name=dev.name,
                        interface_name=iface.name,
                        related_device_id=other_dev.id,
                        title=f"Interfaz {iface.name} en {dev.name} está administrativamente apagada",
                        description=f"La interfaz {iface.name} que conecta con {other_dev.name} tiene estado 'administratively down'.",
                        hint_level1="En equipos Cisco IOS, ¿cuál es el estado por defecto de las interfaces de un router al encenderlo y qué comando se requiere?",
                        hint_level2=f"Accede a {dev.name}, entra al modo de configuración de la interfaz {iface.name} y habilítala.",
                        technical_solution=(
                            f"{dev.name}# configure terminal\n"
                            f"{dev.name}(config)# interface {iface.name}\n"
                            f"{dev.name}(config-if)# no shutdown"
                        )
                    )
                )

    # 2. Interfaz física base de Router apagada teniendo subinterfaces
    for dev in topology.devices:
        subinterfaces = [i for i in dev.interfaces if "." in i.name]
        for sub_if in subinterfaces:
            base_name = sub_if.name.split(".")[0]
            base_if = next((i for i in dev.interfaces if i.name == base_name), None)
            if base_if and base_if.status == InterfaceStatus.ADMIN_DOWN:
                findings.append(
                    DiagnosticFinding(
                        id=f"parent_if_down_{dev.id}_{base_name.replace('/', '_')}",
                        rule_id="RULE_L1_PARENT_INTERFACE_SHUTDOWN",
                        severity=DiagnosticSeverity.ERROR,
                        layer="L1",
                        device_id=dev.id,
                        device_name=dev.name,
                        interface_name=base_name,
                        title=f"Interfaz física base {base_name} apagada en {dev.name}",
                        description=(
                            f"La interfaz física base {base_name} está en 'shutdown'. "
                            f"Sus subinterfaces lógicas (ej: {sub_if.name}) no podrán cursar tráfico hasta levantar la física."
                        ),
                        hint_level1="Si la interfaz física principal está apagada, ¿pueden funcionar sus subinterfaces virtuales asociadas?",
                        hint_level2=f"Asegúrate de ejecutar 'no shutdown' sobre {base_name} (la interfaz física padre), no solo en las subinterfaces.",
                        technical_solution=(
                            f"{dev.name}# configure terminal\n"
                            f"{dev.name}(config)# interface {base_name}\n"
                            f"{dev.name}(config-if)# no shutdown"
                        )
                    )
                )

    return findings
