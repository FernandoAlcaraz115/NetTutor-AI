import re
from typing import List, Dict, Optional, Tuple
from app.core.models import Device, DeviceType, Interface, InterfaceStatus, SwitchportMode

class CiscoIOSParser:
    """
    Parser robusto para archivos 'show running-config' de Cisco IOS (Switches y Routers).
    """

    @staticmethod
    def parse_config(config_text: str, default_device_id: Optional[str] = None) -> Device:
        lines = [line.strip() for line in config_text.splitlines()]
        
        hostname = "Device"
        device_type = DeviceType.ROUTER
        interfaces: List[Interface] = []
        default_gateway: Optional[str] = None
        vlans: Dict[int, str] = {}
        static_routes: List[Dict[str, str]] = []

        current_iface: Optional[Dict] = None
        in_vlan_block = False
        current_vlan_id: Optional[int] = None

        for line in lines:
            # Hostname
            if line.startswith("hostname "):
                hostname = line.split()[1]

            # Detectar tipo por comandos característicos
            if "switchport" in line or "vtp mode" in line:
                device_type = DeviceType.SWITCH

            # Default Gateway
            if line.startswith("ip default-gateway "):
                default_gateway = line.split()[2]

            # Rutas estáticas
            if line.startswith("ip route "):
                parts = line.split()
                if len(parts) >= 4:
                    static_routes.append({
                        "network": parts[2],
                        "mask": parts[3],
                        "next_hop": parts[4] if len(parts) > 4 else ""
                    })

            # Bloque VLAN (vlan 10, vlan 20)
            vlan_match = re.match(r"^vlan\s+(\d+)$", line, re.IGNORECASE)
            if vlan_match:
                in_vlan_block = True
                current_vlan_id = int(vlan_match.group(1))
                vlans[current_vlan_id] = f"VLAN_{current_vlan_id}"
                continue

            if in_vlan_block:
                if line.startswith("name "):
                    vlans[current_vlan_id] = line.split(maxsplit=1)[1]
                    in_vlan_block = False
                elif line.startswith("!") or line.startswith("interface"):
                    in_vlan_block = False

            # Bloque de Interfaz
            if line.startswith("interface "):
                if current_iface:
                    interfaces.append(CiscoIOSParser._build_interface(current_iface))
                
                if_name = line.split(maxsplit=1)[1]
                current_iface = {
                    "name": if_name,
                    "ip_address": None,
                    "subnet_mask": None,
                    "status": InterfaceStatus.UP, # Por defecto up salvo que se encuentre 'shutdown'
                    "switchport_mode": SwitchportMode.NONE,
                    "access_vlan": None,
                    "trunk_allowed_vlans": None,
                    "native_vlan": 1,
                    "encapsulation_dot1q": None
                }
                continue

            if current_iface:
                # IP Address
                ip_match = re.match(r"^ip\s+address\s+([0-9\.]+)\s+([0-9\.]+)", line, re.IGNORECASE)
                if ip_match:
                    current_iface["ip_address"] = ip_match.group(1)
                    current_iface["subnet_mask"] = ip_match.group(2)

                # Shutdown
                if line.lower() == "shutdown":
                    current_iface["status"] = InterfaceStatus.ADMIN_DOWN
                elif line.lower() == "no shutdown":
                    current_iface["status"] = InterfaceStatus.UP

                # Switchport Mode
                if "switchport mode trunk" in line.lower():
                    current_iface["switchport_mode"] = SwitchportMode.TRUNK
                elif "switchport mode access" in line.lower():
                    current_iface["switchport_mode"] = SwitchportMode.ACCESS

                # Access VLAN
                acc_vlan_match = re.search(r"switchport\s+access\s+vlan\s+(\d+)", line, re.IGNORECASE)
                if acc_vlan_match:
                    current_iface["access_vlan"] = int(acc_vlan_match.group(1))
                    if current_iface["switchport_mode"] == SwitchportMode.NONE:
                        current_iface["switchport_mode"] = SwitchportMode.ACCESS

                # Encapsulation dot1Q (Router subinterface: encapsulation dot1Q 10)
                dot1q_match = re.search(r"encapsulation\s+dot1q\s+(\d+)", line, re.IGNORECASE)
                if dot1q_match:
                    current_iface["encapsulation_dot1q"] = int(dot1q_match.group(1))

                # Delimitador de bloque
                if line.startswith("!"):
                    interfaces.append(CiscoIOSParser._build_interface(current_iface))
                    current_iface = None

        if current_iface:
            interfaces.append(CiscoIOSParser._build_interface(current_iface))

        dev_id = default_device_id or hostname.lower().replace(" ", "_")
        return Device(
            id=dev_id,
            name=hostname,
            type=device_type,
            interfaces=interfaces,
            default_gateway=default_gateway,
            vlans=vlans,
            static_routes=static_routes,
            raw_config=config_text
        )

    @staticmethod
    def _build_interface(data: Dict) -> Interface:
        return Interface(
            name=data["name"],
            ip_address=data["ip_address"],
            subnet_mask=data["subnet_mask"],
            status=data["status"],
            switchport_mode=data["switchport_mode"],
            access_vlan=data["access_vlan"],
            trunk_allowed_vlans=data["trunk_allowed_vlans"],
            native_vlan=data["native_vlan"],
            encapsulation_dot1q=data["encapsulation_dot1q"]
        )
