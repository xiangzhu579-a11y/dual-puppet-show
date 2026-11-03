"""Compile only; does not connect to or program hardware."""
from pathlib import Path
import argparse, os, shutil, subprocess
p=argparse.ArgumentParser()
p.add_argument('--gcc', default=os.environ.get('ARM_GCC', 'arm-none-eabi-gcc'))
a=p.parse_args()
root=Path(__file__).resolve().parent
compiler=shutil.which(a.gcc) or a.gcc
out=root/'Build_Check'
out.mkdir(exist_ok=True)
includes=['src','ra/fsp/inc','ra/fsp/inc/api','ra/fsp/inc/instances','ra/arm/CMSIS_5/CMSIS/Core/Include','ra_gen','ra_cfg/fsp_cfg/bsp','ra_cfg/fsp_cfg']
flags=['-mcpu=cortex-m33','-mthumb','-mfloat-abi=hard','-mfpu=fpv5-sp-d16','-O2','-g','-std=c99','-fsigned-char','-ffunction-sections','-fdata-sections','-D_RENESAS_RA_','-D_RA_CORE=CM33','-Wall','-Wextra']
for inc in includes: flags.extend(['-I',str(root/inc)])
sources=['ra/fsp/src/bsp/cmsis/Device/RENESAS/Source/startup.c', 'ra/fsp/src/bsp/cmsis/Device/RENESAS/Source/system.c', 'ra/fsp/src/bsp/mcu/all/bsp_clocks.c', 'ra/fsp/src/bsp/mcu/all/bsp_common.c', 'ra/fsp/src/bsp/mcu/all/bsp_delay.c', 'ra/fsp/src/bsp/mcu/all/bsp_group_irq.c', 'ra/fsp/src/bsp/mcu/all/bsp_guard.c', 'ra/fsp/src/bsp/mcu/all/bsp_io.c', 'ra/fsp/src/bsp/mcu/all/bsp_irq.c', 'ra/fsp/src/bsp/mcu/all/bsp_register_protection.c', 'ra/fsp/src/bsp/mcu/all/bsp_rom_registers.c', 'ra/fsp/src/bsp/mcu/all/bsp_sbrk.c', 'ra/fsp/src/bsp/mcu/all/bsp_security.c', 'ra/fsp/src/r_gpt/r_gpt.c', 'ra/fsp/src/r_ioport/r_ioport.c', 'ra/fsp/src/r_sci_uart/r_sci_uart.c', 'ra_gen/common_data.c', 'ra_gen/hal_data.c', 'ra_gen/main.c', 'ra_gen/pin_data.c', 'ra_gen/vector_data.c', 'src/action_player.c', 'src/hal_entry.c', 'src/ra6m5_echo_reference.c']
objects=[]
for source in sources:
    obj=out/(source+'.o')
    obj.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run([compiler,*flags,'-c',str(root/source),'-o',str(obj)],check=True)
    objects.append(str(obj))
shutil.copy2(root/'build_support'/'memory_regions.ld',out/'memory_regions.ld')
elf=out/(root.name+'.elf')
subprocess.run([compiler,*flags,'-T',str(root/'script'/'fsp.ld'),'-Wl,--gc-sections','-Wl,-Map,'+str(out/(root.name+'.map')),'--specs=nano.specs','--specs=nosys.specs','-o',str(elf),'-Wl,--start-group',*objects,'-Wl,--end-group'],cwd=out,check=True)
print('BUILD PASS:',elf)
