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

        # Caso Switch <-> Switch (Trunk en ambos extremos, Native VLAN y Allowed VLANs)
        if dev1.type == DeviceType.SWITCH and dev2.type == DeviceType.SWITCH:
            if1 = next((i for i in dev1.interfaces if i.name == link.source_interface), None)
            if2 = next((i for i in dev2.interfaces if i.name == link.target_interface), None)
            if if1 and if2:
                # 1. Uno es trunk y el otro es access
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
                elif if2.switchport_mode == SwitchportMode.TRUNK and if1.switchport_mode == SwitchportMode.ACCESS:
                    findings.append(
                        DiagnosticFinding(
                            id=f"vlan_trunk_mismatch_{dev1.id}_{if1.name}",
                            rule_id="RULE_L2_SWITCH_TRUNK_MISMATCH",
                            severity=DiagnosticSeverity.ERROR,
                            layer="L2",
                            device_id=dev1.id,
                            device_name=dev1.name,
                            interface_name=if1.name,
                            related_device_id=dev2.id,
                            related_interface_name=if2.name,
                            title="Desajuste de modo Troncal entre Switches",
                            description=(
                                f"El enlace entre {dev1.name} ({if1.name}) y {dev2.name} ({if2.name}) tiene "
                                f"modos incompatibles ({if1.switchport_mode.value} vs {if2.switchport_mode.value})."
                            ),
                            hint_level1="Cuando dos switches se interconectan para compartir VLANs, ¿cómo deben estar configurados ambos extremos del cable?",
                            hint_level2=f"{dev2.name} tiene {if2.name} en troncal, pero {dev1.name} tiene {if1.name} en modo acceso.",
                            technical_solution=(
                                f"Pasa el puerto de {dev1.name} a modo trunk:\n\n"
                                f"{dev1.name}(config)# interface {if1.name}\n"
                                f"{dev1.name}(config-if)# switchport mode trunk"
                            )
                        )
                    )

                # 2. Desajuste de Native VLAN en enlace Trunk
                if if1.switchport_mode == SwitchportMode.TRUNK and if2.switchport_mode == SwitchportMode.TRUNK:
                    nat1 = if1.native_vlan or 1
                    nat2 = if2.native_vlan or 1
                    if nat1 != nat2:
                        findings.append(
                            DiagnosticFinding(
                                id=f"native_vlan_mismatch_{dev1.id}_{dev2.id}",
                                rule_id="RULE_L2_NATIVE_VLAN_MISMATCH",
                                severity=DiagnosticSeverity.ERROR,
                                layer="L2",
                                device_id=dev1.id,
                                device_name=dev1.name,
                                interface_name=if1.name,
                                related_device_id=dev2.id,
                                related_interface_name=if2.name,
                                title="Incompatibilidad de VLAN Nativa (Native VLAN Mismatch)",
                                description=(
                                    f"El enlace troncal entre {dev1.name} ({if1.name}, Native VLAN {nat1}) y "
                                    f"{dev2.name} ({if2.name}, Native VLAN {nat2}) tiene VLANs nativas distintas."
                                ),
                                hint_level1="¿Qué ocurre con el tráfico sin etiquetar (untagged) en un enlace 802.1Q si ambos switches asumen una VLAN nativa diferente?",
                                hint_level2=f"Compara el comando 'switchport trunk native vlan' entre {dev1.name} ({if1.name}) y {dev2.name} ({if2.name}).",
                                technical_solution=(
                                    f"Iguala la VLAN nativa en ambos extremos del enlace troncal:\n\n"
                                    f"{dev2.name}(config)# interface {if2.name}\n"
                                    f"{dev2.name}(config-if)# switchport trunk native vlan {nat1}"
                                )
                            )
                        )

                    # 3. Verificar si trunk_allowed_vlans bloquea VLANs activas en los switches
                    for sw_dev, sw_if, peer_dev in [(dev1, if1, dev2), (dev2, if2, dev1)]:
                        if sw_if.trunk_allowed_vlans is not None:
                            # VLANs en uso en el switch (definidas o asignadas a puertos de acceso)
                            active_vlans = set(sw_dev.vlans.keys()) | {
                                i.access_vlan for i in sw_dev.interfaces if i.access_vlan and i.access_vlan > 1
                            }
                            missing_vlans = sorted(v for v in active_vlans if v not in sw_if.trunk_allowed_vlans)
                            if missing_vlans:
                                missing_str = ", ".join(str(v) for v in missing_vlans)
                                all_needed = sorted(set(sw_if.trunk_allowed_vlans) | set(missing_vlans))
                                all_needed_str = ",".join(str(v) for v in all_needed)
                                findings.append(
                                    DiagnosticFinding(
                                        id=f"trunk_pruned_vlans_{sw_dev.id}_{sw_if.name.replace('/', '_')}",
                                        rule_id="RULE_L2_TRUNK_ALLOWED_VLANS_MISSING",
                                        severity=DiagnosticSeverity.ERROR,
                                        layer="L2",
                                        device_id=sw_dev.id,
                                        device_name=sw_dev.name,
                                        interface_name=sw_if.name,
                                        related_device_id=peer_dev.id,
                                        title=f"VLANs activas bloqueadas en enlace Troncal ({sw_dev.name})",
                                        description=(
                                            f"El puerto troncal {sw_if.name} en {sw_dev.name} restringe las VLANs permitidas a "
                                            f"{sw_if.trunk_allowed_vlans}, dejando sin paso a las VLANs activas: {missing_str}."
                                        ),
                                        hint_level1=(
                                            "Aunque un enlace esté en modo Trunk, ¿qué sucede si la lista de VLANs permitidas "
                                            "('allowed vlan') omite algunas de las VLANs donde hay PCs conectadas?"
                                        ),
                                        hint_level2=(
                                            f"Inspecciona la interfaz {sw_if.name} en {sw_dev.name}. El filtro 'switchport trunk allowed vlan' "
                                            f"está bloqueando el tráfico de las VLANs {missing_str} hacia {peer_dev.name}."
                                        ),
                                        technical_solution=(
                                            f"Permite las VLANs faltantes en el troncal de {sw_dev.name}:\n\n"
                                            f"{sw_dev.name}# configure terminal\n"
                                            f"{sw_dev.name}(config)# interface {sw_if.name}\n"
                                            f"{sw_dev.name}(config-if)# switchport trunk allowed vlan {all_needed_str}"
                                        )
                                    )
                                )

    return findings
