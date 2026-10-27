"""In-memory index of the existing ClickUp contacts, for matching."""
from .fields import FIELDS, task_url
from .normalize import norm_email, norm_li, norm_name, norm_phone, split_list


class Index:
    def __init__(self):
        self.by_id = {}
        self.by_key = {"google_id": {}, "linkedin_url": {}, "whatsapp": {}}
        self.by_email, self.by_phone, self.by_token = {}, {}, {}
        self.warnings = []

    def add(self, rec):
        tid, v = rec["id"], rec["v"]
        self.by_id[tid] = rec
        for kf, m in self.by_key.items():
            k = v.get(kf)
            if kf == "linkedin_url" and k:
                k = norm_li(k) or k
            if kf == "whatsapp" and k:
                k = norm_phone(k) or k
            if not k:
                continue
            other = m.get(k)
            if other and other != tid:
                self.warnings.append(f"{FIELDS[kf]} {k} is on two tasks: {task_url(other)} and {task_url(tid)}")
            else:
                m[k] = tid
        for e in split_list(v.get("emails")) + [v.get("email") or ""]:
            if norm_email(e):
                self.by_email.setdefault(norm_email(e), set()).add(tid)
        for p in split_list(v.get("phones")):
            if norm_phone(p):
                self.by_phone.setdefault(norm_phone(p), set()).add(tid)
        for t in norm_name(rec["name"]).split():
            self.by_token.setdefault(t, set()).add(tid)

    def get_key(self, kf, k):
        tid = self.by_key[kf].get(k)
        return self.by_id.get(tid) if tid else None

    def snapshot(self):
        """Plain-data copy of every indexed contact (what the run saw before writing)."""
        return [{"id": r["id"], "name": r["name"], "v": r["v"]} for r in self.by_id.values()]


def build_index(cu, progress=None):
    ix = Index()
    for t in cu.all_tasks(progress=progress):
        if t.get("archived"):
            continue
        ix.add({"id": t["id"], "name": t.get("name", ""), "v": {k: cu.decode(t, k) for k in FIELDS}})
    return ix
