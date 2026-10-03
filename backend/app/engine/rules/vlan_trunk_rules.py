from typing import List
from app.core.models import Topology, DeviceType, SwitchportMode, DiagnosticFinding, DiagnosticSeverity

def check_vlan_trunk_rules(topology: Topology) -> List[DiagnosticFinding]:
    """
    Verifica reglas de Capa 2 relacionadas con VLANs, enlaces troncales y acceso.
    """
    findings: List[DiagnosticFinding] = []
    device_map = {d.id: d for d in topology.devices}

    for link in topology.links:
        dev1 = device_map.get(link.source_device)
        dev2 = device_map.get(link.target_device)
        if not dev1 or not dev2:
            continue

        # Identificar casos Switch <-> Router (Router-on-a-stick)
        sw = None
        sw_if_name = None
        router = None
        router_if_name = None

        if dev1.type == DeviceType.SWITCH and dev2.type == DeviceType.ROUTER:
            sw, sw_if_name = dev1, link.source_interface
            router, router_if_name = dev2, link.target_interface
        elif dev2.type == DeviceType.SWITCH and dev1.type == DeviceType.ROUTER:
            sw, sw_if_name = dev2, link.target_interface
            router, router_if_name = dev1, link.source_interface

        if sw and router:
            sw_if = next((i for i in sw.interfaces if i.name == sw_if_name), None)
            
            # Buscar subinterfaces en el router para esa interfaz física (ej: Fa0/0.10 para Fa0/0)
            base_router_if = router_if_name.split(".")[0]
            subinterfaces = [
                i for i in router.interfaces 
                if i.name.startswith(base_router_if + ".") and i.encapsulation_dot1q is not None
            ]

            if subinterfaces and sw_if:
                # Si el router tiene subinterfaces dot1q pero el switch no está en trunk
                if sw_if.switchport_mode != SwitchportMode.TRUNK:
                    findings.append(
                        DiagnosticFinding(
                            id=f"vlan_trunk_err_{sw.id}_{sw_if.name}",
                            rule_id="RULE_L2_TRUNK_REQUIRED_FOR_SUBIFS",
                            severity=DiagnosticSeverity.ERROR,
                            layer="L2",
                            device_id=sw.id,
                            device_name=sw.name,
                            interface_name=sw_if.name,
                            related_device_id=router.id,
                            related_interface_name=router_if_name,
                            title="Puerto de enlace con Router-on-a-stick no es Troncal",
                            description=(
                                f"El puerto {sw_if.name} en el switch {sw.name} está configurado en modo "
                                f"'{sw_if.switchport_mode.value}', pero se conecta a {router.name} ({router_if_name}) "
                                f"que tiene {len(subinterfaces)} subinterfaces 802.1Q."
                            ),
                            hint_level1=(
                                "¿Qué tipo de enlace necesitas cuando un mismo cable debe transportar "
                                "tráfico etiquetado de múltiples VLANs hacia un router?"
                            ),
                            hint_level2=(
                                f"Revisa la interfaz {sw_if.name} de {sw.name}. Actualmente opera como puerto de acceso "
                                f"o sin modo explícito. El router {router.name} espera tramas con etiquetas 802.1Q."
                            ),
                            technical_solution=(
                                f"Configura el puerto de {sw.name} como troncal:\n\n"
                                f"{sw.name}# configure terminal\n"
                                f"{sw.name}(config)# interface {sw_if.name}\n"
                                f"{sw.name}(config-if)# switchport mode trunk\n"
                                f"{sw.name}(config-if)# no shutdown"
                            )
                        )
                    )

        # Caso Switch <-> Switch (Trunk en ambos extremos)
        if dev1.type == DeviceType.SWITCH and dev2.type == DeviceType.SWITCH:
            if1 = next((i for i in dev1.interfaces if i.name == link.source_interface), None)
            if2 = next((i for i in dev2.interfaces if i.name == link.target_interface), None)
            if if1 and if2:
                # Uno es trunk y el otro es access
                if if1.switchport_mode == SwitchportMode.TRUNK and if2.switchport_mode == SwitchportMode.ACCESS:
                    findings.append(
                        DiagnosticFinding(
                            id=f"vlan_trunk_mismatch_{dev2.id}_{if2.name}",
                            rule_id="RULE_L2_SWITCH_TRUNK_MISMATCH",
                            severity=DiagnosticSeverity.ERROR,
                            layer="L2",
                            device_id=dev2.id,
                            device_name=dev2.name,
                            interface_name=if2.name,
                            related_device_id=dev1.id,
                            related_interface_name=if1.name,
                            title="Desajuste de modo Troncal entre Switches",
                            description=(
                                f"El enlace entre {dev1.name} ({if1.name}) y {dev2.name} ({if2.name}) tiene "
                                f"modos incompatibles ({if1.switchport_mode.value} vs {if2.switchport_mode.value})."
                            ),
                            hint_level1="Cuando dos switches se interconectan para compartir VLANs, ¿cómo deben estar configurados ambos extremos del cable?",
                            hint_level2=f"{dev1.name} tiene {if1.name} en troncal, pero {dev2.name} tiene {if2.name} en modo acceso.",
                            technical_solution=(
                                f"Pasa el puerto de {dev2.name} a modo trunk:\n\n"
                                f"{dev2.name}(config)# interface {if2.name}\n"
                                f"{dev2.name}(config-if)# switchport mode trunk"
                            )
                        )
                    )

    return findings
