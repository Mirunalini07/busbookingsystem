import time
import threading
from queue import Queue

class Logger:
    def __init__(self):
        self.logs = []
        self.disk_write_times = []
        self.total_logs_written = 0
        self.queue = Queue()

        self.logger_thread = threading.Thread(target=self.process_logs) #create new thread
        self.logger_thread.daemon = True
        self.logger_thread.start()

    def log(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self.logs.append(entry)
        self.queue.put(entry)
    def process_logs(self):
        while True:
            message = self.queue.get()
            print(message)
            success = False
            retries = 3
            while not success and retries > 0:
                try:
                    start = time.perf_counter()
                    with open("archive.log", "a", encoding="utf-8") as file:
                        file.write(message + "\n")
                    end = time.perf_counter()
                    write_time_ms = (end - start) * 1000
                    self.disk_write_times.append(write_time_ms)
                    self.total_logs_written += 1
                    success = True
                except Exception as e:
                    retries -= 1
                    print(f"Error writing to archive.log: {e}. Retries left: {retries}")
                    if retries > 0:
                        time.sleep(0.5)
            
            self.queue.task_done()

            if success and self.total_logs_written % 5 == 0:
                try:
                    self.show_disk_io_stats()
                except Exception as e:
                    print(f"Error showing disk IO stats: {e}")
    def show_disk_io_stats(self):
        if not self.disk_write_times:
            print("No Disk I/O recorded.")
            return

        total_writes = self.total_logs_written
        average = sum(self.disk_write_times) / total_writes
        throughput_per_ms = total_writes / max(average, 0.000001) if average > 0 else 0
        throughput_per_sec = throughput_per_ms * 1000

        print("\n===== DISK I/O STATISTICS =====")
        print(f"Total Logs Written : {total_writes}")
        print(f"Average Write Time : {average:.4f} ms")
        print(f"Throughput : {throughput_per_sec:.2f} logs/sec")
        print(f"Maximum Write Time : {max(self.disk_write_times):.4f} ms")
        print(f"Minimum Write Time : {min(self.disk_write_times):.4f} ms")
        print("===============================\n")