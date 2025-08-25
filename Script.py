"""
TP Redes Integrador + Netmiko
Script de automatización de configuración y verificación de red segmentada
Autor: Martina Quiroz
"""


from netmiko import ConnectHandler
from datetime import datetime
import paramiko


# --- Parche Paramiko para switches Cisco con SSH legacy ---
paramiko.transport.Transport._preferred_kex = (
    'diffie-hellman-group14-sha1',
    'diffie-hellman-group-exchange-sha1',
    'diffie-hellman-group1-sha1',
)
paramiko.transport.Transport._preferred_keys = (
    'ssh-rsa',
)


# ---- Credenciales ----
CISCO_USER = "admin"
CISCO_PASS = "admin"
CISCO_SECRET = "admin"
MIKROTIK_USER = "admin"
MIKROTIK_PASS = "admin"


LOG_FILE = "netmiko_log.txt"


# ---- Dispositivos ----
switches = [
    {
        'device_type': 'cisco_ios',
        'ip': '10.10.14.2',   # Switch57
        'username': CISCO_USER,
        'password': CISCO_PASS,
        'secret': CISCO_SECRET,
    },
    {
        'device_type': 'cisco_ios',
        'ip': '10.10.14.3',   # Switch56
        'username': CISCO_USER,
        'password': CISCO_PASS,
        'secret': CISCO_SECRET,
    }
]


routers = [
    {
        'device_type': 'mikrotik_routeros',
        'ip': '10.10.14.1',   # Router Principal
        'username': MIKROTIK_USER,
        'password': MIKROTIK_PASS,
    },
    {
        'device_type': 'mikrotik_routeros',
        'ip': '10.10.14.4',   # Router Remoto
        'username': MIKROTIK_USER,
        'password': MIKROTIK_PASS,
    }
]


# ---- VLANs ----
vlans = [
    {'id': 250, 'name': 'Ventas',     'ports': ['e0/1']},
    {'id': 251, 'name': 'Tecnica',    'ports': ['e0/3']},
    {'id': 252, 'name': 'Visitantes', 'ports': ['e1/1']}
]
TRUNK_IF = "e0/0"
ALLOWED_VLANS = [str(v['id']) for v in vlans] + ["1499"]


# ---- Logger ----
def log_event(event):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {event}\n")


# ---- Funciones ----
def ejecutar_comandos(conn, comandos, device_ip):
    cambios, errores = [], []
    for cmd in comandos:
        try:
            resultado = conn.send_config_set([cmd])
            if "Invalid input" in resultado or "Error" in resultado:
                errores.append((cmd, resultado.strip()))
                log_event(f"ERROR en {device_ip}: {cmd} -> {resultado.strip()}")
            else:
                cambios.append((cmd, resultado.strip()))
                log_event(f"OK en {device_ip}: {cmd} -> {resultado.strip()}")
        except Exception as e:
            errores.append((cmd, str(e)))
            log_event(f"EXCEPCIÓN en {device_ip}: {cmd} -> {str(e)}")
    return cambios, errores


def configurar_switch(switch):
    print(f"\n=== Configurando Switch {switch['ip']} ===")
    try:
        conn = ConnectHandler(**switch)
        conn.enable()


        cambios, errores = [], []


        # Crear VLANs
        for vlan in vlans:
            bloque = [
                f"vlan {vlan['id']}",
                f"name {vlan['name']}"
            ]
            try:
                out = conn.send_config_set(bloque)
                cambios.append((f"VLAN {vlan['id']}", out.strip()))
                log_event(f"OK en {switch['ip']}: VLAN {vlan['id']}")
            except Exception as e:
                errores.append((f"VLAN {vlan['id']}", str(e)))
                log_event(f"ERROR en {switch['ip']}: VLAN {vlan['id']} -> {str(e)}")


        # Configurar interfaces de acceso
        for vlan in vlans:
            for port in vlan['ports']:
                bloque = [
                    f"interface {port}",
                    "switchport mode access",
                    f"switchport access vlan {vlan['id']}",
                    "no shutdown"
                ]
                try:
                    out = conn.send_config_set(bloque)
                    cambios.append((f"interface {port}", out.strip()))
                    log_event(f"OK en {switch['ip']}: interface {port}")
                except Exception as e:
                    errores.append((f"interface {port}", str(e)))
                    log_event(f"ERROR en {switch['ip']}: interface {port} -> {str(e)}")


        # Config trunk
        bloque_trunk = [
            f"interface {TRUNK_IF}",
            "switchport mode trunk",
            f"switchport trunk allowed vlan {','.join(ALLOWED_VLANS)}",
            "no shutdown"
        ]
        try:
            out = conn.send_config_set(bloque_trunk)
            cambios.append(("Trunk", out.strip()))
            log_event(f"OK en {switch['ip']}: trunk {TRUNK_IF}")
        except Exception as e:
            errores.append(("Trunk", str(e)))
            log_event(f"ERROR en {switch['ip']}: trunk {TRUNK_IF} -> {str(e)}")


        # Mostrar resultados
        print("\n-- Cambios realizados --")
        for cmd, _ in cambios:
            print(f"✔ {cmd}")
        if errores:
            print("\n-- Errores encontrados --")
            for cmd, err in errores:
                print(f"✘ {cmd} -> {err}")


        print("\n-- Verificación --")
        print(conn.send_command("show vlan brief"))
        print(conn.send_command("show interfaces trunk"))
        conn.disconnect()


    except Exception as e:
        print(f"!! Error al conectar con {switch['ip']}: {str(e)}")




def configurar_mikrotik(router):
    print(f"\n=== Configurando MikroTik {router['ip']} ===")
    try:
        conn = ConnectHandler(**router)
        comandos = []
        if router['ip'] == "10.10.14.1":  # Router Principal
            comandos = [
                # VLAN Ventas
                '/interface vlan add name=Ventas vlan-id=250 interface=ether2',
                '/ip address add address=10.10.14.33/27 interface=Ventas',
                # VLAN Técnica
                '/interface vlan add name=Tecnica vlan-id=251 interface=ether2',
                '/ip address add address=10.10.14.65/28 interface=Tecnica',
                # VLAN Visitantes
                '/interface vlan add name=Visitantes vlan-id=252 interface=ether2',
                '/ip address add address=10.10.14.81/29 interface=Visitantes',
                # NAT
                '/ip firewall nat add chain=srcnat src-address=10.10.14.32/27 action=masquerade comment="NAT Ventas"',
                '/ip firewall nat add chain=srcnat src-address=10.10.14.64/28 action=masquerade comment="NAT Tecnica"',
                # DHCP Ventas
                '/ip pool add name=pool_ventas ranges=10.10.14.34-10.10.14.60',
                '/ip dhcp-server add name=dhcp_ventas interface=Ventas address-pool=pool_ventas lease-time=1h disabled=no',
                '/ip dhcp-server network add address=10.10.14.32/27 gateway=10.10.14.33 dns-server=8.8.8.8',
            ]
        elif router['ip'] == "10.10.14.4":  # Router Remoto
            comandos = [
                '/ip route add dst-address=10.10.14.32/27 gateway=10.10.14.1',
                '/ip route add dst-address=10.10.14.64/28 gateway=10.10.14.1',
                '/ip route add dst-address=10.10.14.80/29 gateway=10.10.14.1',
            ]
        for cmd in comandos:
            conn.send_command(cmd)
        print("\n-- Verificación --")
        print(conn.send_command('/interface vlan print'))
        print(conn.send_command('/ip address print'))
        print(conn.send_command('/ip route print'))
        conn.disconnect()
    except Exception as e:
        print(f"!! Error al conectar con {router['ip']}: {str(e)}")


def main():
    print("=== Automatización de red (Netmiko) ===")
    log_event("=== INICIO EJECUCIÓN ===")
    for sw in switches: configurar_switch(sw)
    for rt in routers: configurar_mikrotik(rt)
    log_event("=== FIN EJECUCIÓN ===")


if __name__ == "__main__":
    main()


