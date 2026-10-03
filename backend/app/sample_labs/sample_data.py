from app.core.models import (
    Topology, Device, DeviceType, Interface, InterfaceStatus, SwitchportMode, Link
)

def get_sample_intervlan_lab() -> Topology:
    """
    Laboratorio piloto: 'Inter-VLAN Routing con Router-on-a-Stick'
    Contiene deliberadamente:
    1. Puerto S1 Fa0/1 conectado a R1 configurado como 'access' en vez de 'trunk'.
    2. PC2 tiene Default Gateway fuera de su subred (192.168.10.1 en vez de 192.168.20.1).
    """
    
    # 1. Router R1
    r1 = Device(
        id="R1",
        name="R1",
        type=DeviceType.ROUTER,
        interfaces=[
            Interface(
                name="FastEthernet0/0",
                status=InterfaceStatus.UP,
                ip_address=None
            ),
            Interface(
                name="FastEthernet0/0.10",
                status=InterfaceStatus.UP,
                ip_address="192.168.10.1",
                subnet_mask="255.255.255.0",
                encapsulation_dot1q=10
            ),
            Interface(
                name="FastEthernet0/0.20",
                status=InterfaceStatus.UP,
                ip_address="192.168.20.1",
                subnet_mask="255.255.255.0",
                encapsulation_dot1q=20
            ),
        ],
        pos_x=450.0,
        pos_y=90.0,
        raw_config=(
            "hostname R1\n"
            "interface FastEthernet0/0\n"
            " no shutdown\n"
            "!\n"
            "interface FastEthernet0/0.10\n"
            " encapsulation dot1Q 10\n"
            " ip address 192.168.10.1 255.255.255.0\n"
            "!\n"
            "interface FastEthernet0/0.20\n"
            " encapsulation dot1Q 20\n"
            " ip address 192.168.20.1 255.255.255.0\n"
            "!"
        )
    )

    # 2. Switch S1
    s1 = Device(
        id="S1",
        name="S1",
        type=DeviceType.SWITCH,
        vlans={10: "Estudiantes", 20: "Profesores"},
        interfaces=[
            # ¡ERROR INTENCIONAL: puerto hacia R1 configurado en ACCESS en vez de TRUNK!
            Interface(
                name="FastEthernet0/1",
                status=InterfaceStatus.UP,
                switchport_mode=SwitchportMode.ACCESS,
                access_vlan=1
            ),
            Interface(
                name="FastEthernet0/10",
                status=InterfaceStatus.UP,
                switchport_mode=SwitchportMode.ACCESS,
                access_vlan=10
            ),
            Interface(
                name="FastEthernet0/20",
                status=InterfaceStatus.UP,
                switchport_mode=SwitchportMode.ACCESS,
                access_vlan=20
            ),
        ],
        pos_x=450.0,
        pos_y=250.0,
        raw_config=(
            "hostname S1\n"
            "vlan 10\n name Estudiantes\n!\n"
            "vlan 20\n name Profesores\n!\n"
            "interface FastEthernet0/1\n"
            " switchport mode access\n" # <--- ERROR
            "!\n"
            "interface FastEthernet0/10\n"
            " switchport access vlan 10\n"
            " switchport mode access\n"
            "!\n"
            "interface FastEthernet0/20\n"
            " switchport access vlan 20\n"
            " switchport mode access\n"
            "!"
        )
    )

    # 3. PC1 (VLAN 10)
    pc1 = Device(
        id="PC1",
        name="PC1",
        type=DeviceType.PC,
        default_gateway="192.168.10.1",
        interfaces=[
            Interface(
                name="FastEthernet0",
                status=InterfaceStatus.UP,
                ip_address="192.168.10.50",
                subnet_mask="255.255.255.0"
            )
        ],
        pos_x=220.0,
        pos_y=420.0
    )

    # 4. PC2 (VLAN 20)
    # ¡ERROR INTENCIONAL: default gateway incorrecto (192.168.10.1 en vez de 192.168.20.1)!
    pc2 = Device(
        id="PC2",
        name="PC2",
        type=DeviceType.PC,
        default_gateway="192.168.10.1", # <--- ERROR: subred equivocada
        interfaces=[
            Interface(
                name="FastEthernet0",
                status=InterfaceStatus.UP,
                ip_address="192.168.20.50",
                subnet_mask="255.255.255.0"
            )
        ],
        pos_x=680.0,
        pos_y=420.0
    )

    # Enlaces físicos
    links = [
        Link(
            id="link_s1_r1",
            source_device="S1",
            source_interface="FastEthernet0/1",
            target_device="R1",
            target_interface="FastEthernet0/0"
        ),
        Link(
            id="link_pc1_s1",
            source_device="PC1",
            source_interface="FastEthernet0",
            target_device="S1",
            target_interface="FastEthernet0/10"
        ),
        Link(
            id="link_pc2_s1",
            source_device="PC2",
            source_interface="FastEthernet0",
            target_device="S1",
            target_interface="FastEthernet0/20"
        )
    ]

    return Topology(
        id="lab1_intervlan",
        name="Práctica 1: Inter-VLAN Routing con Router-on-a-stick",
        description="Configuración de VLAN 10 (Estudiantes) y VLAN 20 (Profesores) con enrutamiento entre ellas mediante R1.",
        devices=[r1, s1, pc1, pc2],
        links=links,
        rubric={
            "goal": "Lograr comunicación ICMP bidireccional entre PC1 (VLAN 10) y PC2 (VLAN 20).",
            "vlans": [10, 20],
            "trunk_link": "S1:Fa0/1 <-> R1:Fa0/0"
        }
    )
