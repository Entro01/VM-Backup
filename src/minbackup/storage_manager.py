import os
import time

class StorageManager:
    def __init__(self, config):
        self.config = config
        self.retention_count = self.config.data['backup']['destinations'][0]['retention']['count']
        self.retention_days = self.config.data['backup']['destinations'][0]['retention']['days']
        self.path = self.config.data['backup']['destinations'][0]['path']

    def list_backups(self):
        backups = [f for f in os.listdir(self.path) if f.endswith('.tar.gz')]
        backups.sort(reverse=True)
        for b in backups:
            print(b)
        return backups

    def cleanup_old_backups(self):
        backups = self.list_backups()
        # Remove by count
        if len(backups) > self.retention_count:
            to_remove = backups[self.retention_count:]
            for f in to_remove:
                try:
                    os.remove(os.path.join(self.path, f))
                    meta = os.path.join(self.path, f + ".meta")
                    if os.path.exists(meta):
                        os.remove(meta)
                except Exception as e:
                    print(f"Failed to remove {f}: {e}")

        # Remove by age
        now = time.time()
        for f in backups:
            fp = os.path.join(self.path, f)
            if os.stat(fp).st_mtime < now - self.retention_days * 86400:
                try:
                    os.remove(fp)
                    meta = fp + ".meta"
                    if os.path.exists(meta):
                        os.remove(meta)
                except Exception as e:
                    print(f"Failed to remove {f}: {e}")

    def get_total_backup_size(self):
        total = 0
        for f in os.listdir(self.path):
            if f.endswith('.tar.gz'):
                total += os.path.getsize(os.path.join(self.path, f))
        print(f"Total backup size: {total / (1024*1024):.2f} MB")
        return total