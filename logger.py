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
            start = time.perf_counter()
            with open("archive.log", "a") as file:
                file.write(message + "\n")
            end = time.perf_counter()
            write_time_ms = (end - start) * 1000
            self.disk_write_times.append(write_time_ms)
            self.total_logs_written += 1
            self.queue.task_done()

            if self.total_logs_written % 5 == 0:
                self.show_disk_io_stats()
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