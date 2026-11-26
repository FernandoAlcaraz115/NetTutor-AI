"""
Decodificador y desencriptador de archivos .pkt / .pka de Cisco Packet Tracer.

Implementa en Python puro (sin dependencias C externas) el pipeline criptográfico
obtenido mediante ingeniería inversa del binario de Cisco Packet Tracer (7.3+ / 8.x / 9.x):
  1. Stage 1 (De-ofuscación inicial): Inversión de bytes + XOR posicional dependiente del tamaño.
  2. Stage 2 (Twofish-128 en modo EAX / CTR + OMAC):
     - Clave estática de 128 bits: 0x89 repetido 16 veces (b'\\x89' * 16)
     - Nonce/IV estático de 128 bits: 0x10 repetido 16 veces (b'\\x10' * 16)
  3. Stage 3 (De-ofuscación secundaria): XOR progresivo ((longitud - índice) & 0xFF).
  4. Stage 4 (Descompresión Qt qUncompress / zlib): Omite los 4 bytes de cabecera big-endian
     y descomprime el flujo deflate para obtener el XML nativo de Packet Tracer.
"""

import re
import zlib
import struct
from pathlib import Path
from typing import Union

_STRUCT_4I = struct.Struct("<4I")
_STRUCT_2Q_BE = struct.Struct(">2Q")

# Expresión regular para limpiar caracteres de control ASCII (ej. ^C en banner motd)
# que son inválidos en el estándar XML 1.0.
_INVALID_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Tablas fijas de permutación de nibbles t0..t3 para construir q0 y q1 (Especificación Twofish)
_T_TABLES = [
    [
        [0x8, 0x1, 0x7, 0xD, 0x6, 0xF, 0x3, 0x2, 0x0, 0xB, 0x5, 0x9, 0xE, 0xC, 0xA, 0x4],
        [0xE, 0xC, 0xB, 0x8, 0x1, 0x2, 0x3, 0x5, 0xF, 0x4, 0xA, 0x6, 0x7, 0x0, 0x9, 0xD],
        [0xB, 0xA, 0x5, 0xE, 0x6, 0xD, 0x9, 0x0, 0xC, 0x8, 0xF, 0x3, 0x2, 0x4, 0x7, 0x1],
        [0xD, 0x7, 0xF, 0x4, 0x1, 0x2, 0x6, 0xE, 0x9, 0xB, 0x3, 0x0, 0x8, 0x5, 0xC, 0xA],
    ],
    [
        [0x2, 0x8, 0xB, 0xD, 0xF, 0x7, 0x6, 0xE, 0x3, 0x1, 0x9, 0x4, 0x0, 0xA, 0xC, 0x5],
        [0x1, 0xE, 0x2, 0xB, 0x4, 0xC, 0x3, 0x7, 0x6, 0xD, 0xA, 0x5, 0xF, 0x9, 0x0, 0x8],
        [0x4, 0xC, 0x7, 0x5, 0x1, 0x6, 0x9, 0xA, 0x0, 0xE, 0xD, 0x8, 0x2, 0xB, 0x3, 0xF],
        [0xB, 0x9, 0x5, 0x1, 0xC, 0x3, 0xD, 0xE, 0x6, 0x4, 0x7, 0xF, 0x2, 0x0, 0x8, 0xA],
    ],
]

_MDS_MATRIX = [
    [0x01, 0xEF, 0x5B, 0x5B],
    [0x5B, 0xEF, 0xEF, 0x01],
    [0xEF, 0x5B, 0x01, 0xEF],
    [0xEF, 0x01, 0xEF, 0x5B],
]

_RS_MATRIX = [
    [0x01, 0xA4, 0x55, 0x87, 0x5A, 0x58, 0xDB, 0x9E],
    [0xA4, 0x56, 0x82, 0xF3, 0x1E, 0xC6, 0x68, 0xE5],
    [0x02, 0xA1, 0xFC, 0xC1, 0x47, 0xAE, 0x3D, 0x19],
    [0xA4, 0x55, 0x87, 0x5A, 0x58, 0xDB, 0x9E, 0x03],
]


def _ror4(x: int, n: int) -> int:
    return ((x >> n) | ((x << (4 - n)) & 0xF)) & 0xF


def _build_q_table(t: list) -> list:
    q = [0] * 256
    for x in range(256):
        a0, b0 = (x >> 4) & 0xF, x & 0xF
        a1 = a0 ^ b0
        b1 = a0 ^ _ror4(b0, 1) ^ ((8 * a0) & 0xF)
        a2, b2 = t[0][a1], t[1][b1]
        a3 = a2 ^ b2
        b3 = a2 ^ _ror4(b2, 1) ^ ((8 * a2) & 0xF)
        a4, b4 = t[2][a3], t[3][b3]
        q[x] = (b4 << 4) | a4
    return q


_Q = [_build_q_table(_T_TABLES[0]), _build_q_table(_T_TABLES[1])]


def _gf_mult(a: int, b: int, poly: int) -> int:
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= poly & 0xFF
        b >>= 1
    return p


def _rol32(x: int, n: int) -> int:
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


class Twofish128:
    """Implementación optimizada en Python puro del cifrador por bloques Twofish-128."""

    def __init__(self, key: bytes):
        if len(key) != 16:
            raise ValueError("Twofish128 requiere una clave de exactamente 16 bytes.")

        words = _STRUCT_4I.unpack(key)
        Me = [words[0], words[2]]
        Mo = [words[1], words[3]]

        self.S = [0, 0]
        for i in range(2):
            k_bytes = key[8 * i : 8 * i + 8]
            s_bytes = [0] * 4
            for row in range(4):
                val = 0
                for col in range(8):
                    val ^= _gf_mult(_RS_MATRIX[row][col], k_bytes[col], 0x14D)
                s_bytes[row] = val
            self.S[1 - i] = struct.unpack("<I", bytes(s_bytes))[0]

        self.sbox = [[0] * 256 for _ in range(4)]
        s0_b = struct.pack("<I", self.S[0])
        s1_b = struct.pack("<I", self.S[1])

        q0, q1 = _Q[0], _Q[1]
        for x in range(256):
            y0 = q1[q0[q0[x] ^ s0_b[0]] ^ s1_b[0]]
            y1 = q0[q0[q1[x] ^ s0_b[1]] ^ s1_b[1]]
            y2 = q1[q1[q0[x] ^ s0_b[2]] ^ s1_b[2]]
            y3 = q0[q1[q1[x] ^ s0_b[3]] ^ s1_b[3]]

            for idx, y in enumerate((y0, y1, y2, y3)):
                b0 = _gf_mult(_MDS_MATRIX[0][idx], y, 0x169)
                b1 = _gf_mult(_MDS_MATRIX[1][idx], y, 0x169)
                b2 = _gf_mult(_MDS_MATRIX[2][idx], y, 0x169)
                b3 = _gf_mult(_MDS_MATRIX[3][idx], y, 0x169)
                self.sbox[idx][x] = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)

        self.K = [0] * 40
        rho = 0x01010101
        for i in range(20):
            A = self._h(2 * i * rho, Me)
            B = _rol32(self._h((2 * i + 1) * rho, Mo), 8)
            self.K[2 * i] = (A + B) & 0xFFFFFFFF
            self.K[2 * i + 1] = _rol32((A + 2 * B) & 0xFFFFFFFF, 9)

    def _h(self, X: int, L: list) -> int:
        x_b = struct.pack("<I", X)
        l0_b = struct.pack("<I", L[0])
        l1_b = struct.pack("<I", L[1])
        q0, q1 = _Q[0], _Q[1]
        y0 = q1[q0[q0[x_b[0]] ^ l1_b[0]] ^ l0_b[0]]
        y1 = q0[q0[q1[x_b[1]] ^ l1_b[1]] ^ l0_b[1]]
        y2 = q1[q1[q0[x_b[2]] ^ l1_b[2]] ^ l0_b[2]]
        y3 = q0[q1[q1[x_b[3]] ^ l1_b[3]] ^ l0_b[3]]
        res = [0] * 4
        for row in range(4):
            res[row] = (
                _gf_mult(_MDS_MATRIX[row][0], y0, 0x169)
                ^ _gf_mult(_MDS_MATRIX[row][1], y1, 0x169)
                ^ _gf_mult(_MDS_MATRIX[row][2], y2, 0x169)
                ^ _gf_mult(_MDS_MATRIX[row][3], y3, 0x169)
            )
        return struct.unpack("<I", bytes(res))[0]

    def encrypt_block(self, block: bytes) -> bytes:
        s0, s1, s2, s3 = self.sbox
        K = self.K
        R0, R1, R2, R3 = _STRUCT_4I.unpack(block)
        R0 ^= K[0]
        R1 ^= K[1]
        R2 ^= K[2]
        R3 ^= K[3]

        for r in range(8, 40, 2):
            T0 = s0[R0 & 0xFF] ^ s1[(R0 >> 8) & 0xFF] ^ s2[(R0 >> 16) & 0xFF] ^ s3[(R0 >> 24) & 0xFF]
            R1_rol = ((R1 << 8) | (R1 >> 24)) & 0xFFFFFFFF
            T1 = s0[R1_rol & 0xFF] ^ s1[(R1_rol >> 8) & 0xFF] ^ s2[(R1_rol >> 16) & 0xFF] ^ s3[(R1_rol >> 24) & 0xFF]

            F0 = (T0 + T1 + K[r]) & 0xFFFFFFFF
            F1 = (T0 + (T1 << 1) + K[r + 1]) & 0xFFFFFFFF

            x2 = R2 ^ F0
            new_R2 = ((x2 >> 1) | ((x2 & 1) << 31)) & 0xFFFFFFFF
            new_R3 = (((R3 << 1) | (R3 >> 31)) & 0xFFFFFFFF) ^ F1
            R0, R1, R2, R3 = new_R2, new_R3, R0, R1

        return _STRUCT_4I.pack(R2 ^ K[4], R3 ^ K[5], R0 ^ K[6], R1 ^ K[7])


def _gf128_double(val: int) -> int:
    msb = (val >> 127) & 1
    res = (val << 1) & ((1 << 128) - 1)
    return res ^ 0x87 if msb else res


def _omac_t(cipher: Twofish128, t: int, msg: bytes) -> bytes:
    L_int = int.from_bytes(cipher.encrypt_block(b"\x00" * 16), "big")
    L_u = _gf128_double(L_int)
    L_u2 = _gf128_double(L_u)

    data = (b"\x00" * 15 + bytes([t])) + msg
    n_blocks = (len(data) + 15) // 16

    state = 0
    for i in range(n_blocks - 1):
        blk = int.from_bytes(data[16 * i : 16 * (i + 1)], "big")
        state = int.from_bytes(cipher.encrypt_block((state ^ blk).to_bytes(16, "big")), "big")

    last = data[16 * (n_blocks - 1) :]
    if len(last) == 16:
        last_int = int.from_bytes(last, "big") ^ L_u
    else:
        padded = last + b"\x80" + b"\x00" * (16 - len(last) - 1)
        last_int = int.from_bytes(padded, "big") ^ L_u2

    return cipher.encrypt_block((state ^ last_int).to_bytes(16, "big"))


# Instancia pre-inicializada para la llave fija de Cisco Packet Tracer (0x89 * 16)
# y su contador inicial OMAC_0(0x10 * 16)
_PT_CIPHER = Twofish128(b"\x89" * 16)
_PT_INITIAL_CTR = int.from_bytes(_omac_t(_PT_CIPHER, 0, b"\x10" * 16), "big")


class PktDecoder:
    """Decodificador de archivos binarios .pkt y .pka de Cisco Packet Tracer a XML."""

    # Límite máximo de XML descomprimido (50 MB) para evitar zip-bombs / exceso de RAM
    MAX_DECOMPRESSED_BYTES = 50 * 1024 * 1024

    @classmethod
    def _safe_zlib_decompress(cls, data: bytes) -> bytes:
        decompressor = zlib.decompressobj()
        out = decompressor.decompress(data, cls.MAX_DECOMPRESSED_BYTES + 1)
        if len(out) > cls.MAX_DECOMPRESSED_BYTES or not decompressor.eof:
            raise ValueError("El archivo .pkt/.pka descomprimido excede el límite seguro (50 MB) o está truncado.")
        return out

    @classmethod
    def decode_bytes_to_xml(cls, raw_bytes: bytes) -> str:
        """
        Recibe los bytes crudos de un archivo .pkt o .pka y devuelve el documento XML limpio.
        Soporta archivos de Packet Tracer 7.3 / 8.x / 9.x (Twofish-EAX) y versiones
        anteriores (XOR clásico).
        """
        # Si el archivo ya estuviera en XML plano
        if raw_bytes.lstrip().startswith(b"<PACKETTRACER5"):
            raw_xml = raw_bytes.decode("utf-8", errors="replace")
            return _INVALID_XML_CHARS_RE.sub("", raw_xml)

        length = len(raw_bytes)
        if length < 20:
            raise ValueError("El archivo .pkt/.pka es demasiado pequeño o está corrupto.")

        try:
            # Etapa 1: Desofuscación inicial (inversión + máscara XOR posicional)
            # (length - i * length) & 0xFF == (length * (1 - i)) & 0xFF
            rev = raw_bytes[::-1]
            l_byte = length & 0xFF
            stage1 = bytes((b ^ ((l_byte * (1 - i)) & 0xFF)) for i, b in enumerate(rev))

            # Etapa 2: Descifrado Twofish-128 EAX (CTR)
            ct = stage1[:-16]
            ct_len = len(ct)
            decrypted = bytearray(ct_len)

            ctr = _PT_INITIAL_CTR
            encrypt_block = _PT_CIPHER.encrypt_block
            full_blocks = (ct_len // 16) * 16

            for offset in range(0, full_blocks, 16):
                ks = encrypt_block(_STRUCT_2Q_BE.pack((ctr >> 64) & 0xFFFFFFFFFFFFFFFF, ctr & 0xFFFFFFFFFFFFFFFF))
                ctr += 1
                c0, c1 = _STRUCT_2Q_BE.unpack_from(ct, offset)
                k0, k1 = _STRUCT_2Q_BE.unpack(ks)
                _STRUCT_2Q_BE.pack_into(decrypted, offset, c0 ^ k0, c1 ^ k1)

            if full_blocks < ct_len:
                ks = encrypt_block(_STRUCT_2Q_BE.pack((ctr >> 64) & 0xFFFFFFFFFFFFFFFF, ctr & 0xFFFFFFFFFFFFFFFF))
                for j in range(ct_len - full_blocks):
                    decrypted[full_blocks + j] = ct[full_blocks + j] ^ ks[j]

            # Etapa 3: Desofuscación secundaria
            stage3 = bytes((b ^ ((ct_len - i) & 0xFF)) for i, b in enumerate(decrypted))

            # Etapa 4: Descompresión zlib segura (omitiendo los 4 bytes de tamaño Qt qUncompress)
            xml_bytes = cls._safe_zlib_decompress(stage3[4:])
        except ValueError:
            raise
        except Exception:
            # Fallback para formato clásico Packet Tracer 5.x - 7.2 (XOR simple + zlib)
            try:
                legacy = bytes((b ^ ((length - i) & 0xFF)) for i, b in enumerate(raw_bytes))
                xml_bytes = cls._safe_zlib_decompress(legacy[4:])
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(
                    "No se pudo desencriptar el archivo .pkt/.pka. Puede estar corrupto o provenir "
                    "de una versión de Packet Tracer con un cifrado no soportado."
                ) from exc

        xml_str = xml_bytes.decode("utf-8", errors="replace")
        return _INVALID_XML_CHARS_RE.sub("", xml_str)

    @classmethod
    def decode_file_to_xml(cls, file_path: Union[str, Path]) -> str:
        path = Path(file_path)
        return cls.decode_bytes_to_xml(path.read_bytes())

