"""
Parser de topologías completas desde archivos .pkt de Cisco Packet Tracer.
Convierte el XML desencriptado de Packet Tracer en el modelo unificado `Topology`
de NetTutorIA (Dispositivos, Interfaces, VLANs, Configuraciones IOS y Enlaces).
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Set, Tuple, Union

from app.core.models import (
    Device,
    DeviceType,
    Interface,
    InterfaceStatus,
    Link,
    SwitchportMode,
    Topology,
)
from app.parser.cisco_ios_parser import CiscoIOSParser
from app.parser.pkt_decoder import PktDecoder


class PktParser:
    """Extrae objetos Topology a partir de archivos binarios .pkt o bytes crudos."""

    # Tipos de dispositivos internos de PT que no son nodos de red lógicos
    IGNORED_PT_TYPES = {
        "power distribution device",
        "patch panel",
        "wall mount",
        "copper repeater",
    }

    # Caché en memoria: (ruta_resuelta, mtime_ns, size) -> Topology
    _FILE_CACHE: Dict[Tuple[str, int, int], Topology] = {}

    @classmethod
    def parse_file(cls, file_path: Union[str, Path], topology_id: str = None) -> Topology:
        path = Path(file_path).resolve()
        stat = path.stat()
        cache_key = (str(path), stat.st_mtime_ns, stat.st_size)
        cached = cls._FILE_CACHE.get(cache_key)
        if cached is not None:
            return cached.model_copy(deep=True)

        xml_str = PktDecoder.decode_file_to_xml(path)
        lab_id = topology_id or path.stem.lower().replace(" ", "_")
        topo = cls.parse_xml(xml_str, topology_id=lab_id, default_name=path.stem)

        # Limitar tamaño del caché en memoria a 30 archivos recientes
        if len(cls._FILE_CACHE) >= 30:
            cls._FILE_CACHE.pop(next(iter(cls._FILE_CACHE)))
        cls._FILE_CACHE[cache_key] = topo
        return topo.model_copy(deep=True)

    @classmethod
    def parse_bytes(cls, raw_bytes: bytes, filename: str = "Practica.pkt") -> Topology:
        xml_str = PktDecoder.decode_bytes_to_xml(raw_bytes)
        stem = Path(filename).stem
        lab_id = stem.lower().replace(" ", "_")
        return cls.parse_xml(xml_str, topology_id=lab_id, default_name=stem)

    @staticmethod
    def _select_student_network(root: ET.Element) -> ET.Element:
        """
        En archivos .pka existen múltiples bloques <NETWORK> (ej. red del estudiante y red solución
        del Activity Wizard). Selecciona únicamente el <NETWORK> principal del estudiante.
        """
        # 1. En .pkt estándar: <PACKETTRACER5><NETWORK>
        direct_net = root.find("NETWORK")
        if direct_net is not None:
            return direct_net

        # 2. En .pka: <PACKETTRACER5_ACTIVITY><PACKETTRACER5><NETWORK>
        pka_student_net = root.find("PACKETTRACER5/NETWORK")
        if pka_student_net is not None:
            return pka_student_net

        # 3. Fallback: primer <NETWORK> que contenga <DEVICES>
        for net in root.findall(".//NETWORK"):
            if net.find("DEVICES") is not None:
                return net
        return root

    @classmethod
    def parse_xml(cls, xml_str: str, topology_id: str = "pkt_lab", default_name: str = "Práctica Packet Tracer") -> Topology:
        root = ET.fromstring(xml_str)
        pt_version = root.findtext("VERSION") or root.findtext("PACKETTRACER5/VERSION") or "8.x"
        network_el = cls._select_student_network(root)

        # 1. Mapear SAVE_REF_ID -> ID único del dispositivo (evitando colisiones si hay nombres repetidos)
        ref_to_device_id: Dict[str, str] = {}
        dev_el_to_id: Dict[int, str] = {}
        used_ids: Dict[str, int] = {}
        connected_ports_by_dev: Dict[str, Set[str]] = {}
        raw_devices_xml = network_el.findall("./DEVICES/DEVICE")

        for dev_el in raw_devices_xml:
            eng = dev_el.find("ENGINE")
            if eng is None:
                continue
            pt_type = (eng.findtext("TYPE") or "").strip()
            if pt_type.lower() in cls.IGNORED_PT_TYPES:
                continue

            dev_name = (eng.findtext("NAME") or "Device").strip()
            count = used_ids.get(dev_name, 0)
            used_ids[dev_name] = count + 1
            unique_id = dev_name if count == 0 else f"{dev_name}_{count + 1}"

            dev_el_to_id[id(dev_el)] = unique_id
            save_ref = (eng.findtext("SAVE_REF_ID") or "").strip()
            if save_ref:
                ref_to_device_id[save_ref] = unique_id
            connected_ports_by_dev.setdefault(unique_id, set())

        # 2. Extraer enlaces físicos (<LINKS><LINK><CABLE>) únicamente de la red del estudiante
        links: List[Link] = []
        raw_links_xml = network_el.findall("./LINKS/LINK")
        for idx, link_el in enumerate(raw_links_xml):
            cable = link_el.find("CABLE")
            if cable is None:
                continue

            from_ref = (cable.findtext("FROM") or "").strip()
            to_ref = (cable.findtext("TO") or "").strip()
            src_dev = ref_to_device_id.get(from_ref)
            tgt_dev = ref_to_device_id.get(to_ref)
            if not src_dev or not tgt_dev:
                continue

            ports = [(p.text or "").strip() for p in cable.findall("PORT")]
            src_port = ports[0] if len(ports) > 0 and ports[0] else "FastEthernet0"
            tgt_port = ports[1] if len(ports) > 1 and ports[1] else "FastEthernet0"

            connected_ports_by_dev.setdefault(src_dev, set()).add(src_port)
            connected_ports_by_dev.setdefault(tgt_dev, set()).add(tgt_port)

            functional = (cable.findtext("FUNCTIONAL") or "true").strip().lower() == "true"
            cable_type_raw = (cable.findtext("TYPE") or "").strip().lower()
            if "serial" in cable_type_raw:
                link_type = "serial"
            elif "fiber" in cable_type_raw:
                link_type = "fiber"
            elif "cross" in cable_type_raw:
                link_type = "copper_cross"
            else:
                link_type = "copper_straight"

            links.append(
                Link(
                    id=f"link_{idx+1}_{src_dev}_{tgt_dev}",
                    source_device=src_dev,
                    source_interface=src_port,
                    target_device=tgt_dev,
                    target_interface=tgt_port,
                    link_type=link_type,
                    status="up" if functional else "down",
                )
            )

        # 3. Extraer dispositivos (<DEVICES><DEVICE>)
        devices: List[Device] = []
        for dev_el in raw_devices_xml:
            eng = dev_el.find("ENGINE")
            if eng is None:
                continue

            pt_type_raw = (eng.findtext("TYPE") or "").strip()
            if pt_type_raw.lower() in cls.IGNORED_PT_TYPES:
                continue

            dev_name = (eng.findtext("NAME") or "Device").strip()
            unique_id = dev_el_to_id.get(id(dev_el), dev_name)
            dev_type = cls._map_device_type(pt_type_raw)

            # Coordenadas lógicas en el lienzo de Packet Tracer
            ws_logical = dev_el.find("WORKSPACE/LOGICAL")
            pos_x = float(ws_logical.findtext("X") or 400.0) if ws_logical is not None else 400.0
            pos_y = float(ws_logical.findtext("Y") or 250.0) if ws_logical is not None else 250.0

            # Extraer RUNNINGCONFIG si existe (Routers y Switches)
            rc_lines = [line.text or "" for line in eng.findall("RUNNINGCONFIG/LINE")]
            raw_config = "\n".join(rc_lines).strip()

            if raw_config and dev_type in (DeviceType.ROUTER, DeviceType.SWITCH):
                parsed_dev = CiscoIOSParser.parse_config(raw_config, default_device_id=unique_id)
                parsed_dev.id = unique_id
                parsed_dev.name = dev_name
                parsed_dev.type = dev_type
                parsed_dev.pos_x = pos_x
                parsed_dev.pos_y = pos_y

                # Extraer VLANs desde la base de datos XML (<VLAN number="10" name="Faculty"/>)
                xml_vlans = cls._extract_xml_vlans(eng)
                if xml_vlans:
                    parsed_dev.vlans.update(xml_vlans)

                # Filtrar interfaces irrelevantes (dejar conectadas, con IP, trunk o VLAN asignada)
                conn_ports = connected_ports_by_dev.get(unique_id, set())
                filtered_ifs = [
                    iface
                    for iface in parsed_dev.interfaces
                    if (
                        iface.name in conn_ports
                        or iface.ip_address is not None
                        or iface.switchport_mode == SwitchportMode.TRUNK
                        or (iface.access_vlan is not None and iface.access_vlan != 1)
                        or "." in iface.name
                    )
                ]
                parsed_dev.interfaces = filtered_ifs or parsed_dev.interfaces[:4]
                devices.append(parsed_dev)
            else:
                # Host final (PC, Laptop, Server)
                gw = (eng.findtext("GATEWAY") or "").strip()
                if gw in ("", "0.0.0.0", "None"):
                    gw = None

                host_ifs = cls._extract_host_interfaces(eng, connected_ports_by_dev.get(unique_id, set()))
                devices.append(
                    Device(
                        id=unique_id,
                        name=dev_name,
                        type=dev_type,
                        interfaces=host_ifs,
                        default_gateway=gw,
                        pos_x=pos_x,
                        pos_y=pos_y,
                    )
                )

        # 4. Normalizar coordenadas (pos_x, pos_y) para encuadrar en el visor SVG
        cls._normalize_coordinates(devices)

        # Resumen descriptivo automático
        routers_n = sum(1 for d in devices if d.type == DeviceType.ROUTER)
        switches_n = sum(1 for d in devices if d.type == DeviceType.SWITCH)
        hosts_n = sum(1 for d in devices if d.type in (DeviceType.PC, DeviceType.SERVER))
        desc = (
            f"Archivo Packet Tracer (v{pt_version}) · "
            f"{switches_n} Switch(es), {routers_n} Router(s), {hosts_n} Host(s), {len(links)} enlaces."
        )

        return Topology(
            id=topology_id,
            name=f"Práctica PKT: {default_name}",
            description=desc,
            devices=devices,
            links=links,
            rubric={
                "source_format": "Cisco Packet Tracer (.pkt)",
                "pt_version": pt_version,
            },
        )

    @staticmethod
    def _map_device_type(pt_type: str) -> DeviceType:
        t = pt_type.lower()
        if "router" in t:
            return DeviceType.ROUTER
        if "switch" in t or "bridge" in t:
            return DeviceType.SWITCH
        if "server" in t:
            return DeviceType.SERVER
        return DeviceType.PC

    @staticmethod
    def _extract_xml_vlans(eng_el: ET.Element) -> Dict[int, str]:
        vlans: Dict[int, str] = {}
        for v_el in eng_el.findall(".//VLAN"):
            num_str = v_el.get("number") or v_el.findtext("NUMBER")
            name_str = v_el.get("name") or v_el.findtext("NAME") or ""
            if num_str and num_str.isdigit():
                vid = int(num_str)
                # Ignorar VLANs reservadas FDDI/TokenRing (1002-1005) y default 1
                if 1 < vid < 1002:
                    vlans[vid] = name_str
        return vlans

    @staticmethod
    def _extract_host_interfaces(eng_el: ET.Element, connected_ports: Set[str]) -> List[Interface]:
        interfaces: List[Interface] = []
        default_port_name = next(iter(connected_ports), "FastEthernet0")

        for port_el in eng_el.findall(".//PORT"):
            ptype = (port_el.findtext("TYPE") or "").strip()
            # Ignorar puertos Bluetooth / RS232 / USB sin IP
            ip_addr = (port_el.findtext("IP") or "").strip()
            subnet = (port_el.findtext("SUBNET") or "").strip()
            if not ip_addr and "FastEthernet" not in ptype and "Gigabit" not in ptype:
                continue

            if ip_addr in ("", "0.0.0.0"):
                ip_addr = None
            if subnet in ("", "0.0.0.0"):
                subnet = None

            port_up = (port_el.findtext("PORT_ADMIN_STATUS") or "true").strip().lower() != "false"
            interfaces.append(
                Interface(
                    name=default_port_name if not interfaces else f"FastEthernet{len(interfaces)}",
                    ip_address=ip_addr,
                    subnet_mask=subnet,
                    status=InterfaceStatus.UP if port_up else InterfaceStatus.ADMIN_DOWN,
                )
            )

        if not interfaces:
            interfaces.append(Interface(name=default_port_name, status=InterfaceStatus.UP))
        return interfaces

    @staticmethod
    def _normalize_coordinates(devices: List[Device]) -> None:
        if not devices:
            return
        xs = [d.pos_x for d in devices if d.pos_x is not None]
        ys = [d.pos_y for d in devices if d.pos_y is not None]
        if not xs or not ys:
            return

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Lienzo objetivo adaptativo según la densidad de equipos
        num_devs = len(devices)
        target_min_x = 90.0
        target_min_y = 75.0
        target_max_x = max(780.0, 90.0 + (num_devs * 48.0))
        target_max_y = max(470.0, 75.0 + (num_devs * 22.0))

        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)

        for d in devices:
            if max_x - min_x < 10:
                d.pos_x = 430.0
            else:
                d.pos_x = round(target_min_x + ((d.pos_x - min_x) / span_x) * (target_max_x - target_min_x), 1)

            if max_y - min_y < 10:
                d.pos_y = 260.0
            else:
                d.pos_y = round(target_min_y + ((d.pos_y - min_y) / span_y) * (target_max_y - target_min_y), 1)

        # Separar equipos que hayan quedado exactamente superpuestos
        occupied = set()
        for d in devices:
            key = (round(d.pos_x / 30) * 30, round(d.pos_y / 25) * 25)
            shift = 0
            while key in occupied:
                shift += 1
                d.pos_x += 45.0
                d.pos_y += (25.0 if shift % 2 == 1 else -25.0)
                key = (round(d.pos_x / 30) * 30, round(d.pos_y / 25) * 25)
            occupied.add(key)

