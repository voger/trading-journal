"""Daily Journal tab."""
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QFormLayout, QDateTimeEdit, QPlainTextEdit,
)
from PyQt6.QtCore import QDate
from tabs import BaseTab
from database import get_journal_entry, save_journal_entry


class JournalTab(BaseTab):
    def __init__(self, conn, get_aid_fn, status_bar_fn):
        super().__init__(conn, get_aid_fn)
        self._status = status_bar_fn
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        db_ = QHBoxLayout(); db_.addWidget(QLabel("Date:"))
        self.journal_date = QDateTimeEdit(); self.journal_date.setCalendarPopup(True)
        self.journal_date.setDisplayFormat("yyyy-MM-dd"); self.journal_date.setDate(QDate.currentDate())
        self.journal_date.dateChanged.connect(self.refresh)
        db_.addWidget(self.journal_date)
        b = QPushButton("Today"); b.clicked.connect(lambda: self.journal_date.setDate(QDate.currentDate())); db_.addWidget(b)
        db_.addStretch()
        b = QPushButton("Save Entry"); b.clicked.connect(self._on_save); db_.addWidget(b)
        layout.addLayout(db_)
        form = QFormLayout()
        self.j_cond = QComboBox(); self.j_cond.addItems(['','trending','ranging','volatile','low_volume','mixed'])
        self.j_emot = QComboBox(); self.j_emot.addItems(['','calm','focused','anxious','distracted','overconfident','tired'])
        self.j_plan_f = QComboBox(); self.j_plan_f.addItems(['N/A','Yes','No'])
        self.j_obs = QPlainTextEdit(); self.j_obs.setMinimumHeight(100); self.j_obs.setPlaceholderText("Market observations...")
        self.j_lessons = QPlainTextEdit(); self.j_lessons.setMinimumHeight(80); self.j_lessons.setPlaceholderText("Key takeaways...")
        self.j_tomorrow = QPlainTextEdit(); self.j_tomorrow.setMinimumHeight(80); self.j_tomorrow.setPlaceholderText("Plan for tomorrow...")
        form.addRow("Conditions:", self.j_cond); form.addRow("Emotional State:", self.j_emot)
        form.addRow("Followed Plan?", self.j_plan_f)
        form.addRow("Observations:", self.j_obs); form.addRow("Lessons:", self.j_lessons)
        form.addRow("Tomorrow:", self.j_tomorrow)
        layout.addLayout(form)

    def refresh(self):
        if self.aid() is None:
            self.j_cond.setCurrentIndex(0); self.j_emot.setCurrentIndex(0); self.j_plan_f.setCurrentIndex(0)
            self.j_obs.setPlainText(''); self.j_lessons.setPlainText(''); self.j_tomorrow.setPlainText('')
            return
        ds = self.journal_date.date().toString("yyyy-MM-dd")
        entry = get_journal_entry(self.conn, ds, self.aid())
        if entry:
            for combo, key in [(self.j_cond,'market_conditions'),(self.j_emot,'emotional_state')]:
                i = combo.findText(entry[key] or ''); combo.setCurrentIndex(max(0,i))
            fp = entry['followed_plan']
            self.j_plan_f.setCurrentIndex(0 if fp is None else (1 if fp else 2))
            self.j_obs.setPlainText(entry['observations'] or '')
            self.j_lessons.setPlainText(entry['lessons_learned'] or '')
            self.j_tomorrow.setPlainText(entry['plan_for_tomorrow'] or '')
        else:
            self.j_cond.setCurrentIndex(0); self.j_emot.setCurrentIndex(0); self.j_plan_f.setCurrentIndex(0)
            self.j_obs.setPlainText(''); self.j_lessons.setPlainText(''); self.j_tomorrow.setPlainText('')

    def _on_save(self):
        if self.aid() is None:
            self._status("Select an account before saving a journal entry.")
            return
        ds = self.journal_date.date().toString("yyyy-MM-dd")
        fp_map = {'N/A': None, 'Yes': 1, 'No': 0}
        save_journal_entry(self.conn, ds, self.aid(),
            market_conditions=self.j_cond.currentText() or None,
            emotional_state=self.j_emot.currentText() or None,
            followed_plan=fp_map.get(self.j_plan_f.currentText()),
            observations=self.j_obs.toPlainText().strip() or None,
            lessons_learned=self.j_lessons.toPlainText().strip() or None,
            plan_for_tomorrow=self.j_tomorrow.toPlainText().strip() or None)
        self._status(f"Journal saved for {ds}.")
