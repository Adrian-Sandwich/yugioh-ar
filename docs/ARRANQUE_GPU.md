# Arranque en la computadora con GPU y trabajo con dos sesiones

Fecha: 27/09/2026. Cómo levantar el proyecto en la máquina nueva y cómo
coordinar dos sesiones de Claude Code: una allá, que hace el trabajo pesado,
y una en la laptop, que puede mandar comandos por SSH.

## 1. Poner el repo en la máquina nueva

Dos opciones que se pueden combinar:

- **Zip completo** de la carpeta (sin `.venv*`, `.runtime`, `__pycache__`): trae
  código, `data/`, `downloads/` y `transfer/`.
- **Clon de GitHub** para el código al día: `git clone https://github.com/Adrian-Sandwich/yugioh-ar.git`
  y copiar encima `data/`, `downloads/` y `transfer/` del zip. Si el zip es
  anterior al último commit, un `git pull` dentro de la carpeta lo iguala.

## 2. Instalar

```powershell
nvidia-smi                       # anotar la versión de CUDA que soporta el controlador
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_gpu.ps1 -RestoreDatabases -TorchIndexUrl https://download.pytorch.org/whl/cu128
```

`-RestoreDatabases` copia las tres bases limpias de `transfer/<fecha>/` encima
de `data/` antes de arrancar nada (son las copias hechas con la API de backup;
no hay que restaurarlas sobre una base viva). Cambiar `cu128` por el índice
que corresponda al controlador según https://pytorch.org/get-started/locally/.
El script escribe `research/qa/destino-visores.json` y
`research/qa/destino-pose.json`; el segundo debe decir `cuda_available: true`
y el nombre de la GPU. Si dice CPU, no seguir: revisar controlador e índice.

Luego `start_lab.ps1 -Live`. La IP del teléfono cambia en otra red: pasarla
con `--camera http://IP:8080` en la línea de `camera` de `start_lab.ps1` o
arrancar `camera_viewer.py --backend embedding --ar --camera http://IP:8080`.

## 3. Sesión de Claude Code en la máquina con GPU

Abrir una terminal en la carpeta del repo y arrancar `claude`. Esa sesión no
hereda la memoria de la laptop; lo importante está en los documentos. Primer
mensaje sugerido, tal cual:

```text
Lee README.es.md, research/TRANSFERENCIA_GENERAL.md (bloque de actualización
del 26/09), research/TIEMPO_REAL.md, research/COLA_EXPERIMENTOS.md y
docs/ARRANQUE_GPU.md. Esta es la computadora con GPU. Confirma con
research/qa/destino-pose.json que PyTorch ve la GPU, y luego propón el orden
para los experimentos 5 y 8 de la cola, con lo que falta de datos para cada uno.
No entrenes nada hasta que confirmemos el plan.
```

Si se quiere trasladar también la memoria de la laptop: copiar
`C:\Users\Adrian\.claude\projects\C--Users-Adrian-src-yugioh\memory\` a la
ruta equivalente en la máquina nueva (el nombre de la carpeta codifica la ruta
del repo; si el repo queda en otra ruta, el nombre cambia).

## 4. SSH desde la laptop a la GPU (para la sesión de coordinación)

En la **máquina con GPU**, en PowerShell como administrador:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd; Set-Service sshd -StartupType Automatic
New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -PropertyType String -Force
# Llave pública de la laptop (ver abajo). Para usuarios administradores va en este archivo:
Add-Content C:\ProgramData\ssh\administrators_authorized_keys '<pegar la llave pública>'
icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F'
Restart-Service sshd
ipconfig | findstr IPv4
```

En la **laptop** la llave se genera con `ssh-keygen -t ed25519 -f
$env:USERPROFILE\.ssh\id_ed25519_yugioh -N ''`; la pública es el archivo
`.pub`. Probar: `ssh -i $env:USERPROFILE\.ssh\id_ed25519_yugioh usuario@IP
"cd C:\ruta\yugioh; .\.venv-pose\Scripts\python.exe research\doctor.py --torch"`.

Con eso, la sesión de la laptop puede lanzar entrenamientos, leer resultados y
comparar contra los documentos, mientras la sesión de la GPU edita código y
corre las pruebas localmente. Regla para no pisarse: **una sola sesión edita
el repo a la vez**; la otra sólo lee o lanza comandos. Los cambios viajan por
Git (commit y push desde donde se editó, pull en la otra).

## 5. Qué hacer primero allá

1. `destino-pose.json` con GPU visible.
2. Fotos reales según `research/PROTOCOLO_CAPTURAS.md` (no necesita GPU, pero
   es lo que desbloquea los experimentos 5 y 8).
3. Experimento 8 con lo que ya hay: escaneos por rareza como positivos y
   `research/calibrate_acceptance.py` como arnés antes y después.
4. Experimento 5 (YOLO11) en cuanto haya sesiones anotadas y convertidas con
   `research/yolo11_pose/from_captures.py`.
