"""measure_resources.py

Starts `main.py` (or attaches to an existing PID) and samples CPU and memory
usage over a duration, reporting maximum observed values.

Usage examples:
  python measure_resources.py --script main.py --duration 10 --interval 0.5
  python measure_resources.py --pid 12345 --duration 10 --interval 0.5
"""
import argparse
import time
import os
import sys
import psutil
import subprocess


def human_bytes(n):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(n) < 1024.0:
            return f"{n:3.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def monitor_process(pid, duration, interval):
    proc = psutil.Process(pid)
    # warm up counters
    try:
        proc.cpu_percent(None)
    except Exception:
        pass

    max_proc_cpu = 0.0
    max_rss = 0
    max_vms = 0
    max_sys_cpu = 0.0
    max_sys_idle = 0.0

    end_time = time.time() + duration

    # immediate sample
    try:
        p_cpu = proc.cpu_percent(None)
        mem = proc.memory_info()
        rss = mem.rss
        vms = mem.vms
        sys_cpu = psutil.cpu_percent(None)
        sys_idle = psutil.cpu_times_percent(None).idle

        max_proc_cpu = max(max_proc_cpu, p_cpu)
        max_rss = max(max_rss, rss)
        max_vms = max(max_vms, vms)
        max_sys_cpu = max(max_sys_cpu, sys_cpu)
        max_sys_idle = max(max_sys_idle, sys_idle)
    except psutil.NoSuchProcess:
        return None

    while time.time() < end_time:
        time.sleep(interval)
        try:
            p_cpu = proc.cpu_percent(None)
            mem = proc.memory_info()
            rss = mem.rss
            vms = mem.vms
        except psutil.NoSuchProcess:
            break

        sys_cpu = psutil.cpu_percent(None)
        sys_idle = psutil.cpu_times_percent(None).idle

        max_proc_cpu = max(max_proc_cpu, p_cpu)
        max_rss = max(max_rss, rss)
        max_vms = max(max_vms, vms)
        max_sys_cpu = max(max_sys_cpu, sys_cpu)
        max_sys_idle = max(max_sys_idle, sys_idle)

    return {
        'max_proc_cpu': max_proc_cpu,
        'max_rss': max_rss,
        'max_vms': max_vms,
        'max_sys_cpu': max_sys_cpu,
        'max_sys_idle': max_sys_idle,
    }


def run_script_and_monitor(script, duration, interval):
    cmd = [sys.executable, script]
    # Avoid capturing stdout/stderr to prevent blocking on large output
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        stats = monitor_process(proc.pid, duration, interval)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    return stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--script', default='main.py', help='Script to start and monitor')
    p.add_argument('--pid', type=int, help='Existing PID to monitor')
    p.add_argument('--duration', type=float, default=10.0, help='Monitoring duration seconds')
    p.add_argument('--interval', type=float, default=0.5, help='Sample interval seconds')
    args = p.parse_args()

    if args.pid is None:
        if not os.path.exists(args.script):
            print('Script not found:', args.script)
            sys.exit(2)
        print(f'Starting {args.script} and monitoring for {args.duration}s')
        stats = run_script_and_monitor(args.script, args.duration, args.interval)
    else:
        print(f'Monitoring PID {args.pid} for {args.duration}s')
        stats = monitor_process(args.pid, args.duration, args.interval)

    if stats is None:
        print('Process exited before sampling could be completed.')
        return

    print('\n===== RESOURCE SUMMARY =====')
    print(f"Max process CPU percent: {stats['max_proc_cpu']:.1f}%")
    print(f"Max system CPU percent observed: {stats['max_sys_cpu']:.1f}%")
    print(f"Max system CPU idle observed: {stats['max_sys_idle']:.1f}%")
    print(f"Max process RSS: {human_bytes(stats['max_rss'])}")
    print(f"Max process VMS: {human_bytes(stats['max_vms'])}")
    print('============================')


if __name__ == '__main__':
    main()
