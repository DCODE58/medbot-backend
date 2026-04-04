# chatbot/nlp_processor.py
"""
Medical NLP Processor.

Fix 7: NLTK writes data to ~/nltk_data by default.  On Render free tier the
home directory is read-only after the build phase, so runtime downloads fail.
We read NLTK_DATA from the environment (set to /tmp/nltk_data in render.yaml)
and pass it explicitly to every nltk.download() call.
"""

import os
import re
import logging
from typing import List, Dict

from django.core.cache import cache

logger = logging.getLogger(__name__)

SYMPTOMS_CACHE_KEY      = "nlp:symptoms:v3"
EMERGENCY_CACHE_KEY     = "nlp:emergency:v3"
SYMPTOMS_CACHE_TIMEOUT  = 3600
EMERGENCY_CACHE_TIMEOUT = 3600

# Fix 7: read the writable NLTK data dir from the environment
_NLTK_DATA_DIR: str = os.getenv("NLTK_DATA", "/tmp/nltk_data")


def _ensure_nltk() -> None:
    """Download required NLTK corpora into the writable data directory."""
    import nltk

    # Add our directory to NLTK's search path if it isn't there already
    if _NLTK_DATA_DIR not in nltk.data.path:
        nltk.data.path.insert(0, _NLTK_DATA_DIR)

    for corpus in ("punkt", "punkt_tab", "stopwords", "wordnet"):
        try:
            nltk.download(corpus, download_dir=_NLTK_DATA_DIR, quiet=True)
        except Exception as exc:  # network unavailable etc.
            logger.warning("NLTK download '%s' skipped: %s", corpus, exc)


class MedicalNLPProcessor:
    """
    Two-pass symptom extraction:
      Pass 1 — Symptom records from the database (name + alternative_names).
      Pass 2 — Hardcoded Kenyan / Swahili variation dictionary.

    Emergency detection uses the EmergencyKeyword table.
    Heavy DB results are cached in DatabaseCache for 1 hour.
    """

    def __init__(self) -> None:
        _ensure_nltk()
        self._nlp = None  # spaCy model — lazy-loaded on first use

        self.symptom_variations: Dict[str, List[str]] = {
            "fever": [
                "fever", "hot body", "high temperature", "sweating", "chills",
                "feverish", "joto", "feeling hot", "night sweats", "homa",
                "body is hot", "ninauma joto", "high fever",
            ],
            "headache": [
                "headache", "head pain", "head hurting", "migraine",
                "kichwa kuuma", "throbbing head", "pressure in head",
                "maumivu ya kichwa", "head ache",
            ],
            "cough": [
                "cough", "coughing", "dry cough", "wet cough", "kikohozi",
                "chest cough", "barking cough", "cannot stop coughing",
                "coughing blood", "pink sputum", "productive cough",
            ],
            "fatigue": [
                "fatigue", "tired", "weakness", "exhausted", "lethargy",
                "no energy", "body weak", "uchovu", "udhaifu", "mwili dhaifu",
                "feeling weak", "always tired",
            ],
            "vomiting": [
                "vomit", "vomiting", "throwing up", "nausea", "sick stomach",
                "kutapika", "feel like vomiting", "nauseated",
            ],
            "diarrhea": [
                "diarrhea", "diarrhoea", "loose stools", "running stomach",
                "watery stool", "kuhara", "kutharau", "stomach running",
                "frequent stool", "watery poop", "loose motion",
            ],
            "chest_pain": [
                "chest pain", "chest discomfort", "heart pain", "tight chest",
                "maumivu kifua", "squeezing chest", "chest tightness",
            ],
            "difficulty_breathing": [
                "difficulty breathing", "shortness of breath", "can't breathe",
                "breathing fast", "wheezing", "kupumua shida", "breathless",
                "laboured breathing", "unable to breathe", "hard to breathe",
            ],
            "joint_pain": [
                "joint pain", "joint ache", "arthritis", "pain in joints",
                "knees hurt", "maumivu viungo", "painful joints", "aching joints",
            ],
            "muscle_pain": [
                "muscle pain", "myalgia", "body aches", "sore muscles",
                "whole body pain", "mwili kuuma", "maumivu mwilini",
                "body is aching",
            ],
            "stomach_ache": [
                "stomach ache", "stomach pain", "abdominal pain", "belly pain",
                "tumbo kuuma", "cramping", "tummy hurts", "stomach cramps",
                "lower abdominal pain",
            ],
            "rash": [
                "rash", "skin rash", "red spots", "itching", "hives",
                "skin bumps", "upele", "kuwasha ngozi", "skin itching",
            ],
            "dehydration": [
                "dehydrated", "dry mouth", "sunken eyes", "thirsty", "dark urine",
                "no tears", "very thirsty", "mouth dry", "not urinating",
            ],
            "confusion": [
                "confused", "disoriented", "delirium", "not acting normal",
                "altered mental", "not responding", "behaving strangely",
                "not making sense",
            ],
            "sore_throat": [
                "sore throat", "throat pain", "swallowing difficulty",
                "throat swollen", "koo kuuma", "painful swallow",
                "difficulty swallowing",
            ],
            "dizziness": [
                "dizzy", "dizziness", "lightheaded", "spinning", "vertigo",
                "off balance", "kizunguzungu", "feeling faint",
            ],
            "numbness": [
                "numb", "numbness", "tingling", "pins and needles",
                "loss of feeling", "feet tingling", "hands tingling",
            ],
            "swelling": [
                "swelling", "swollen", "edema", "puffy", "inflamed",
                "kuvimba", "swollen feet", "swollen face", "swollen ankles",
            ],
            "weight_loss": [
                "weight loss", "losing weight", "getting thin",
                "kupoteza uzito", "wasting", "very thin", "dramatic weight loss",
            ],
            "night_sweats": [
                "night sweats", "sweating at night", "waking up sweaty",
                "bedsheets wet from sweat", "drenched in sweat at night",
            ],
            "jaundice": [
                "yellow eyes", "yellow skin", "jaundice", "macho ya njano",
                "yellowing", "eyes are yellow", "skin turning yellow",
            ],
            "blood_cough": [
                "coughing blood", "blood in sputum", "bloody cough",
                "pink sputum", "blood when coughing", "haemoptysis",
            ],
            "frequent_urination": [
                "frequent urination", "urinating often", "passing urine many times",
                "wake up to pee", "mkojo mara nyingi", "always urinating",
            ],
            "burning_urination": [
                "burning urination", "painful urination", "urine burns",
                "pain when urinating", "mkojo kuuma", "burning when peeing",
            ],
            "stiff_neck": [
                "stiff neck", "neck stiffness", "cannot bend neck",
                "shingo ngumu", "neck pain", "rigid neck",
            ],
            "convulsions": [
                "convulsions", "seizure", "fits", "shaking uncontrollably",
                "degedege", "epileptic attack", "jerking", "fitting",
            ],
            "pale_skin": [
                "pale skin", "pallor", "pale gums", "white gums",
                "pale conjunctiva", "inner eyelids pale", "pale face",
            ],
            "itching": [
                "itching", "intense itch", "skin itching", "genital itching",
                "kuwasha", "mwili kuwasha", "scratching all over", "itchy",
            ],
            "discharge": [
                "discharge", "genital discharge", "pus", "yellow discharge",
                "green discharge", "smelly discharge", "vaginal discharge",
            ],
            "eye_pain": [
                "eye pain", "red eyes", "eye discharge", "eye swelling",
                "macho kuuma", "eyes red", "sticky eyes", "pink eye",
            ],
            "ear_pain": [
                "ear pain", "ear discharge", "hearing loss", "masikio kuuma",
                "ears ringing", "ear ache", "pain in ear",
            ],
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    @property
    def nlp(self):
        """Lazy-load spaCy model on first access."""
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_sm")
            except OSError:
                logger.warning("en_core_web_sm not found — downloading …")
                spacy.cli.download("en_core_web_sm")
                self._nlp = spacy.load("en_core_web_sm")
        return self._nlp

    def _db_symptoms(self):
        result = cache.get(SYMPTOMS_CACHE_KEY)
        if result is None:
            from .models import Symptom
            result = list(Symptom.objects.only("id", "name", "alternative_names"))
            cache.set(SYMPTOMS_CACHE_KEY, result, SYMPTOMS_CACHE_TIMEOUT)
        return result

    def _db_emergency_keywords(self):
        result = cache.get(EMERGENCY_CACHE_KEY)
        if result is None:
            from .models import EmergencyKeyword
            result = list(EmergencyKeyword.objects.only("keyword", "severity", "response_message"))
            cache.set(EMERGENCY_CACHE_KEY, result, EMERGENCY_CACHE_TIMEOUT)
        return result

    # ── Public API ────────────────────────────────────────────────────────────

    def extract_symptoms(self, text: str) -> List[str]:
        """Return deduplicated symptom names extracted from free-form text."""
        text_lower = text.lower()
        text_clean = re.sub(r"[^\w\s]", " ", text_lower)
        extracted: List[str] = []

        # Pass 1 — database symptom records
        try:
            for symptom in self._db_symptoms():
                if symptom.name.lower() in text_clean:
                    extracted.append(symptom.name)
                    continue
                if symptom.alternative_names:
                    for alt in symptom.alternative_names.split(","):
                        alt = alt.strip().lower()
                        if alt and alt in text_clean:
                            extracted.append(symptom.name)
                            break
        except Exception as exc:
            logger.error("DB symptom extraction: %s", exc)

        # Pass 2 — hardcoded Kenyan/Swahili variation dictionary
        for sym_key, variations in self.symptom_variations.items():
            for var in variations:
                if var in text_lower:
                    extracted.append(sym_key)
                    break

        # Deduplicate preserving order
        seen: set = set()
        unique: List[str] = []
        for s in extracted:
            s_norm = s.lower()
            if s_norm not in seen:
                seen.add(s_norm)
                unique.append(s)
        return unique

    def detect_emergency(self, text: str) -> List[Dict]:
        """Return list of { keyword, severity, message } for any emergency triggers found."""
        text_lower = text.lower()
        emergencies: List[Dict] = []
        try:
            for kw in self._db_emergency_keywords():
                if kw.keyword.lower() in text_lower:
                    emergencies.append({
                        "keyword":  kw.keyword,
                        "severity": kw.severity,
                        "message":  kw.response_message,
                    })
        except Exception as exc:
            logger.error("detect_emergency: %s", exc)
        return emergencies
