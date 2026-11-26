"""
Emulador y parser interactivo de comandos Cisco IOS para NetTutorIA.
Permite ejecutar comandos en tiempo real sobre la configuración activa del dispositivo:
- enable / disable
- configure terminal / exit / end
- vlan <id> / name <nombre>
- interface <nombre> (incluye subinterfaces dot1Q como Fa0/0.10)
- switchport mode trunk / access
- switchport access vlan <id>
- switchport trunk native vlan <id>
- switchport trunk allowed vlan <lista>
- encapsulation dot1Q <vlan>
- ip address <ip> <mask> / no ip address
- shutdown / no shutdown
- ip default-gateway <ip>
- ip route <net> <mask> <nexthop> / no ip route <net> <mask> [nexthop]
- show running-config / show ip interface brief / show vlan brief
"""

import ipaddress
import re
from typing import Optional
from pydantic import BaseModel
from app.core.models import Device, Interface, InterfaceStatus, SwitchportMode


class CommandExecutionRequest(BaseModel):
    device_id: str
    command: str
    current_mode: str = "user"  # user (>), priv (#), config (config)#, config-if (config-if)#, config-vlan (config-vlan)#
    current_interface: Optional[str] = None


class CommandExecutionResponse(BaseModel):
    output: str
    new_mode: str
    prompt: str
    current_interface: Optional[str] = None
    configuration_changed: bool = False


def _canonical_if_name(name: str) -> str:
    n = (name or "").strip().lower().replace(" ", "")
    n = re.sub(r"^fastethernet", "fa", n)
    n = re.sub(r"^gigabitethernet", "gi", n)
    n = re.sub(r"^tengigabitethernet", "te", n)
    n = re.sub(r"^ethernet", "eth", n)
    n = re.sub(r"^serial", "se", n)
    n = re.sub(r"^loopback", "lo", n)
    return n


def _is_valid_ipv4(val: str) -> bool:
    try:
        ipaddress.IPv4Address(val)
        return True
    except ValueError:
        return False


class CiscoIOSEmulator:

    @classmethod
    def execute(cls, device: Device, req: CommandExecutionRequest) -> CommandExecutionResponse:
        cmd = req.command.strip()
        mode = req.current_mode
        curr_if_name = req.current_interface
        prompt_prefix = device.name

        if not cmd:
            return CommandExecutionResponse(
                output="",
                new_mode=mode,
                prompt=cls._get_prompt(prompt_prefix, mode, curr_if_name),
                current_interface=curr_if_name,
                configuration_changed=False,
            )

        cmd_lower = re.sub(r"\s+", " ", cmd.lower())
        changed = False
        output = ""

        # Comandos EXEC / SHOW / WRITE (incluye prefijo 'do' en modos de configuración)
        is_do_cmd = cmd_lower.startswith("do ")
        exec_cmd = cmd_lower[3:].strip() if is_do_cmd else cmd_lower

        if exec_cmd in ("show ip interface brief", "sh ip int br"):
            if mode in ("user", "priv") or is_do_cmd:
                output = cls._render_ip_int_brief(device)
            else:
                output = "% Invalid input detected. En modo configuración usa 'do show ip interface brief'."
            return cls._build_resp(output, mode, prompt_prefix, curr_if_name, False)

        if exec_cmd in ("show running-config", "sh run"):
            if mode == "priv" or is_do_cmd:
                output = cls._render_running_config(device)
            else:
                output = "% Privileged EXEC mode required (usa 'enable' o 'do sh run')."
            return cls._build_resp(output, mode, prompt_prefix, curr_if_name, False)

        if exec_cmd in ("show vlan brief", "sh vlan br", "show vlan", "sh vlan"):
            if mode in ("user", "priv") or is_do_cmd:
                output = cls._render_vlan_brief(device)
            else:
                output = "% Invalid input detected. En modo configuración usa 'do show vlan brief'."
            return cls._build_resp(output, mode, prompt_prefix, curr_if_name, False)

        if exec_cmd in ("write", "wr", "write memory", "copy run start", "copy running-config startup-config"):
            if mode == "priv" or is_do_cmd:
                output = "Building configuration...\n[OK]"
            else:
                output = "% Privileged EXEC mode required."
            return cls._build_resp(output, mode, prompt_prefix, curr_if_name, False)

        if cmd_lower in ("?", "help"):
            output = (
                "Comandos disponibles:\n"
                "  enable | configure terminal | exit | end\n"
                "  interface <nombre> | vlan <id> | hostname <nombre>\n"
                "  ip address <ip> <mask> | no ip address | shutdown | no shutdown\n"
                "  switchport mode <access|trunk> | switchport access vlan <id>\n"
                "  switchport trunk native vlan <id> | switchport trunk allowed vlan <lista>\n"
                "  encapsulation dot1Q <id> | ip default-gateway <ip> | ip route <net> <mask> <nh>\n"
                "  show running-config | show ip interface brief | show vlan brief | wr"
            )
            return cls._build_resp(output, mode, prompt_prefix, curr_if_name, False)

        # Navegación de modos
        if cmd_lower in ("enable", "en") and mode in ("user", "priv"):
            mode = "priv"
        elif cmd_lower in ("disable", "exit", "quit") and mode == "priv":
            mode = "user"
        elif cmd_lower in ("configure terminal", "conf t", "config t") and mode == "priv":
            mode = "config"
            output = "Enter configuration commands, one per line. End with CNTL/Z."
        elif cmd_lower in ("exit", "end") and mode == "config":
            mode = "priv"
        elif cmd_lower == "end" and mode in ("config-if", "config-vlan"):
            mode = "priv"
            curr_if_name = None
        elif cmd_lower == "exit" and mode in ("config-if", "config-vlan"):
            mode = "config"
            curr_if_name = None

        # Modo CONFIG
        elif mode == "config":
            parts = cmd.split()
            if (cmd_lower.startswith("interface ") or cmd_lower.startswith("int ")) and len(parts) >= 2:
                if_name = cmd.split(maxsplit=1)[1].strip()
                norm_if = cls._find_or_create_interface(device, if_name)
                curr_if_name = norm_if.name
                mode = "config-if"
            elif cmd_lower.startswith("vlan ") and len(parts) == 2:
                try:
                    vid = int(parts[1])
                    if not (1 <= vid <= 4094):
                        raise ValueError()
                    if device.vlans is None:
                        device.vlans = {}
                    device.vlans.setdefault(vid, f"VLAN_{vid}")
                    curr_if_name = str(vid)
                    mode = "config-vlan"
                    changed = True
                except ValueError:
                    output = "% Invalid VLAN ID (debe estar entre 1 y 4094)."
            elif cmd_lower.startswith("hostname ") and len(parts) >= 2:
                new_h = parts[1]
                device.name = new_h
                prompt_prefix = new_h
                changed = True
            elif cmd_lower.startswith("ip default-gateway ") and len(parts) >= 3:
                if _is_valid_ipv4(parts[2]):
                    device.default_gateway = parts[2]
                    changed = True
                else:
                    output = f"% Invalid IP address: {parts[2]}"
            elif cmd_lower.startswith("ip route ") and len(parts) >= 5:
                if _is_valid_ipv4(parts[2]) and _is_valid_ipv4(parts[3]):
                    if device.static_routes is None:
                        device.static_routes = []
                    device.static_routes.append(
                        {"network": parts[2], "mask": parts[3], "next_hop": parts[4]}
                    )
                    changed = True
                else:
                    output = "% Invalid network or subnet mask in 'ip route'."
            elif cmd_lower.startswith("no ip route ") and len(parts) >= 5:
                if device.static_routes is None:
                    device.static_routes = []
                nh_filter = parts[5] if len(parts) >= 6 else None
                device.static_routes = [
                    r
                    for r in device.static_routes
                    if not (
                        r.get("network") == parts[3]
                        and r.get("mask") == parts[4]
                        and (nh_filter is None or r.get("next_hop") == nh_filter)
                    )
                ]
                changed = True
            else:
                output = "% Incomplete or unrecognized command."

        # Modo CONFIG-VLAN
        elif mode == "config-vlan":
            parts = cmd.split(maxsplit=1)
            if cmd_lower.startswith("name ") and len(parts) == 2 and curr_if_name and curr_if_name.isdigit():
                vid = int(curr_if_name)
                if device.vlans is None:
                    device.vlans = {}
                device.vlans[vid] = parts[1].strip()
                changed = True
            else:
                output = "% Incomplete or unrecognized VLAN command."

        # Modo CONFIG-IF
        elif mode == "config-if":
            parts = cmd.split()
            if (cmd_lower.startswith("interface ") or cmd_lower.startswith("int ")) and len(parts) >= 2:
                if_name = cmd.split(maxsplit=1)[1].strip()
                norm_if = cls._find_or_create_interface(device, if_name)
                curr_if_name = norm_if.name
            else:
                target_if = next((i for i in device.interfaces if i.name == curr_if_name), None)
                if not target_if:
                    output = "% Interface context error."
                elif cmd_lower in ("shutdown", "shut"):
                    target_if.status = InterfaceStatus.ADMIN_DOWN
                    output = f"%LINK-5-CHANGED: Interface {target_if.name}, changed state to administratively down"
                    changed = True
                elif cmd_lower in ("no shutdown", "no shut"):
                    target_if.status = InterfaceStatus.UP
                    output = f"%LINK-5-CHANGED: Interface {target_if.name}, changed state to up"
                    changed = True
                elif (cmd_lower.startswith("ip address ") or cmd_lower.startswith("ip add ")) and len(parts) >= 4:
                    if _is_valid_ipv4(parts[2]) and _is_valid_ipv4(parts[3]):
                        target_if.ip_address = parts[2]
                        target_if.subnet_mask = parts[3]
                        changed = True
                    else:
                        output = "% Invalid IP address or subnet mask."
                elif cmd_lower in ("no ip address", "no ip add"):
                    target_if.ip_address = None
                    target_if.subnet_mask = None
                    changed = True
                elif cmd_lower == "switchport mode trunk":
                    target_if.switchport_mode = SwitchportMode.TRUNK
                    changed = True
                elif cmd_lower == "switchport mode access":
                    target_if.switchport_mode = SwitchportMode.ACCESS
                    changed = True
                elif cmd_lower.startswith("switchport access vlan ") and len(parts) >= 4:
                    try:
                        vid = int(parts[3])
                        if not (1 <= vid <= 4094):
                            raise ValueError()
                        target_if.access_vlan = vid
                        target_if.switchport_mode = SwitchportMode.ACCESS
                        changed = True
                    except ValueError:
                        output = "% Invalid VLAN ID (debe estar entre 1 y 4094)."
                elif cmd_lower.startswith("switchport trunk native vlan ") and len(parts) >= 5:
                    try:
                        vid = int(parts[4])
                        if not (1 <= vid <= 4094):
                            raise ValueError()
                        target_if.native_vlan = vid
                        changed = True
                    except ValueError:
                        output = "% Invalid Native VLAN ID."
                elif cmd_lower.startswith("switchport trunk allowed vlan ") and len(parts) >= 5:
                    spec = cmd.split(maxsplit=4)[4].strip()
                    if spec.lower() == "all":
                        target_if.trunk_allowed_vlans = None
                        changed = True
                    else:
                        v_list = []
                        valid = True
                        for p in spec.split(","):
                            p = p.strip()
                            if "-" in p:
                                bounds = p.split("-", 1)
                                if bounds[0].isdigit() and bounds[1].isdigit():
                                    s, e = int(bounds[0]), int(bounds[1])
                                    if 1 <= s <= e <= 4094:
                                        v_list.extend(range(s, e + 1))
                                    else:
                                        valid = False
                                else:
                                    valid = False
                            elif p.isdigit():
                                v = int(p)
                                if 1 <= v <= 4094:
                                    v_list.append(v)
                                else:
                                    valid = False
                            else:
                                valid = False
                        if valid and v_list:
                            target_if.trunk_allowed_vlans = sorted(set(v_list))
                            changed = True
                        else:
                            output = "% Invalid VLAN list. Ejemplo: switchport trunk allowed vlan 10,20,30"
                elif cmd_lower.startswith("encapsulation dot1q ") and len(parts) >= 3:
                    try:
                        vid = int(parts[2])
                        if not (1 <= vid <= 4094):
                            raise ValueError()
                        target_if.encapsulation_dot1q = vid
                        changed = True
                    except ValueError:
                        output = "% Invalid dot1Q VLAN ID."
                else:
                    output = "% Incomplete or unrecognized interface command."

        else:
            output = "% Invalid input detected at '^' marker. Escribe '?' para ver comandos."

        return cls._build_resp(output, mode, prompt_prefix, curr_if_name, changed)

    @classmethod
    def _build_resp(
        cls,
        output: str,
        mode: str,
        prompt_prefix: str,
        curr_if_name: Optional[str],
        changed: bool,
    ) -> CommandExecutionResponse:
        return CommandExecutionResponse(
            output=output,
            new_mode=mode,
            prompt=cls._get_prompt(prompt_prefix, mode, curr_if_name),
            current_interface=curr_if_name,
            configuration_changed=changed,
        )

    @staticmethod
    def _get_prompt(hostname: str, mode: str, if_name: Optional[str]) -> str:
        if mode == "user":
            return f"{hostname}>"
        if mode == "priv":
            return f"{hostname}#"
        if mode == "config":
            return f"{hostname}(config)#"
        if mode == "config-if":
            return f"{hostname}(config-if)#"
        if mode == "config-vlan":
            return f"{hostname}(config-vlan)#"
        return f"{hostname}#"

    @staticmethod
    def _find_or_create_interface(device: Device, name_input: str) -> Interface:
        clean = name_input.strip()
        canon_input = _canonical_if_name(clean)
        for i in device.interfaces:
            if i.name.lower() == clean.lower() or _canonical_if_name(i.name) == canon_input:
                return i

        # Si es subinterfaz nueva dot1Q (e.g. Fa0/0.10) o interfaz nueva
        new_if = Interface(name=clean, status=InterfaceStatus.UP)
        device.interfaces.append(new_if)
        return new_if

    @staticmethod
    def _render_ip_int_brief(device: Device) -> str:
        lines = [
            f"{'Interface':<25} {'IP-Address':<16} {'OK?':<5} {'Method':<8} {'Status':<22} {'Protocol'}",
            f"{'-'*25} {'-'*16} {'-'*5} {'-'*8} {'-'*22} {'-'*8}",
        ]
        for i in device.interfaces:
            ip_str = i.ip_address or "unassigned"
            status_str = "up" if i.status == InterfaceStatus.UP else "administratively down"
            proto_str = "up" if i.status == InterfaceStatus.UP else "down"
            lines.append(f"{i.name:<25} {ip_str:<16} {'YES':<5} {'manual':<8} {status_str:<22} {proto_str}")
        return "\n".join(lines)

    @staticmethod
    def _render_running_config(device: Device) -> str:
        lines = [f"hostname {device.name}", "!"]
        for vid, vname in sorted((device.vlans or {}).items()):
            lines.extend([f"vlan {vid}", f" name {vname}", "!"])

        for i in device.interfaces:
            lines.append(f"interface {i.name}")
            if i.encapsulation_dot1q:
                lines.append(f" encapsulation dot1Q {i.encapsulation_dot1q}")
            if i.ip_address and i.subnet_mask:
                lines.append(f" ip address {i.ip_address} {i.subnet_mask}")
            if i.switchport_mode == SwitchportMode.TRUNK:
                lines.append(" switchport mode trunk")
                if i.native_vlan and i.native_vlan != 1:
                    lines.append(f" switchport trunk native vlan {i.native_vlan}")
                if i.trunk_allowed_vlans:
                    lines.append(f" switchport trunk allowed vlan {','.join(str(v) for v in i.trunk_allowed_vlans)}")
            elif i.switchport_mode == SwitchportMode.ACCESS:
                lines.append(" switchport mode access")
                if i.access_vlan and i.access_vlan != 1:
                    lines.append(f" switchport access vlan {i.access_vlan}")
            if i.status == InterfaceStatus.ADMIN_DOWN:
                lines.append(" shutdown")
            lines.append("!")

        if device.default_gateway:
            lines.append(f"ip default-gateway {device.default_gateway}")

        for r in (device.static_routes or []):
            lines.append(f"ip route {r.get('network')} {r.get('mask')} {r.get('next_hop')}")

        lines.append("end")
        return "\n".join(lines)

    @staticmethod
    def _render_vlan_brief(device: Device) -> str:
        lines = [
            f"{'VLAN':<5} {'Name':<24} {'Status':<10} {'Ports'}",
            f"{'-'*5} {'-'*24} {'-'*10} {'-'*30}",
        ]
        v1_ports = [
            i.name.replace("FastEthernet", "Fa").replace("GigabitEthernet", "Gi")
            for i in device.interfaces
            if i.switchport_mode == SwitchportMode.ACCESS and (i.access_vlan == 1 or i.access_vlan is None)
        ]
        lines.append(f"{'1':<5} {'default':<24} {'active':<10} {', '.join(v1_ports)}")

        for vid, vname in sorted((device.vlans or {}).items()):
            if vid == 1:
                continue
            ports = [
                i.name.replace("FastEthernet", "Fa").replace("GigabitEthernet", "Gi")
                for i in device.interfaces
                if i.switchport_mode == SwitchportMode.ACCESS and i.access_vlan == vid
            ]
            lines.append(f"{str(vid):<5} {vname:<24} {'active':<10} {', '.join(ports)}")
        return "\n".join(lines)
