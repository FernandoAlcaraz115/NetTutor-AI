from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class DeviceType(str, Enum):
    ROUTER = "router"
    SWITCH = "switch"
    PC = "pc"
    SERVER = "server"

class SwitchportMode(str, Enum):
    ACCESS = "access"
    TRUNK = "trunk"
    DYNAMIC = "dynamic"
    NONE = "none"

class InterfaceStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    ADMIN_DOWN = "administratively down"

class Interface(BaseModel):
    name: str
    ip_address: Optional[str] = None
    subnet_mask: Optional[str] = None
    status: InterfaceStatus = InterfaceStatus.UP
    switchport_mode: SwitchportMode = SwitchportMode.NONE
    access_vlan: Optional[int] = None
    trunk_allowed_vlans: Optional[List[int]] = None
    native_vlan: Optional[int] = 1
    encapsulation_dot1q: Optional[int] = None # Subinterface VLAN tag (e.g. Fa0/0.10 -> 10)
    duplex: Optional[str] = "auto"
    speed: Optional[str] = "auto"

class Device(BaseModel):
    id: str
    name: str
    type: DeviceType
    interfaces: List[Interface] = Field(default_factory=list)
    default_gateway: Optional[str] = None
    vlans: Optional[Dict[int, str]] = Field(default_factory=dict) # vlan_id -> vlan_name
    routing_protocols: Optional[List[str]] = Field(default_factory=list) # e.g. ["ospf 1", "static"]
    static_routes: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    raw_config: Optional[str] = None
    pos_x: Optional[float] = 0.0
    pos_y: Optional[float] = 0.0

class Link(BaseModel):
    id: str
    source_device: str
    source_interface: str
    target_device: str
    target_interface: str
    link_type: str = "copper_straight" # copper_straight, copper_cross, serial, fiber
    status: str = "up" # up, down, degraded

class Topology(BaseModel):
    id: str = "default_lab"
    name: str = "Práctica de Red"
    description: Optional[str] = ""
    devices: List[Device] = Field(default_factory=list)
    links: List[Link] = Field(default_factory=list)
    rubric: Optional[Dict[str, Any]] = Field(default_factory=dict)

class DiagnosticSeverity(str, Enum):
    ERROR = "error"     # ❌ Impide la conectividad básica
    WARNING = "warning" # ⚠️ Posible desajuste o mala práctica
    INFO = "info"       # ℹ️ Observación o sugerencia de optimización

class DiagnosticFinding(BaseModel):
    id: str
    rule_id: str
    severity: DiagnosticSeverity
    layer: str = "L2" # L1, L2, L3, L4, L7
    device_id: str
    device_name: str
    interface_name: Optional[str] = None
    related_device_id: Optional[str] = None
    related_interface_name: Optional[str] = None
    title: str
    description: str
    # Niveles de retroalimentación pedagógica
    hint_level1: str # Pregunta conceptual socrática
    hint_level2: str # Orientación de componente / interfaz
    technical_solution: str # Solución explícita y comandos IOS

class DiagnosticReport(BaseModel):
    topology_id: str
    total_issues: int
    errors_count: int
    warnings_count: int
    score_percentage: float
    findings: List[DiagnosticFinding]

class TutorChatRequest(BaseModel):
    topology_id: Optional[str] = "default_lab"
    user_message: str
    selected_finding_id: Optional[str] = None
    hint_level: Optional[int] = 1 # 1: Conceptual, 2: Clave, 3: Respuesta directa
    chat_history: Optional[List[Dict[str, str]]] = Field(default_factory=list)

class TutorChatResponse(BaseModel):
    tutor_reply: str
    hint_level_provided: int
    recommended_next_action: Optional[str] = None
    highlight_devices: Optional[List[str]] = Field(default_factory=list)
    highlight_interfaces: Optional[List[str]] = Field(default_factory=list)
