# chatbot/nlp_processor.py
"""
Medical NLP Processor — NLTK only, no spaCy.

Two-pass symptom extraction:
  Pass 1 — DB Symptom records (name + alternative_names), cached.
  Pass 2 — Hardcoded Kenyan/Swahili variation dictionary.

Emergency detection queries the EmergencyKeyword table, cached.

Fix: extract_symptoms now returns canonical text names (e.g. "abdominal pain")
in addition to DB-normalised names so the RAG retriever can match them against
Disease.common_symptoms which stores human-readable text.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List

import nltk
from django.core.cache import cache
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

logger = logging.getLogger(__name__)

# Download NLTK data to /tmp so it works on Render's read-only home directory
_nltk_data_dir = os.getenv("NLTK_DATA", "/tmp/nltk_data")
os.makedirs(_nltk_data_dir, exist_ok=True)

for _pkg in ("punkt", "punkt_tab", "stopwords", "wordnet"):
    try:
        nltk.download(_pkg, download_dir=_nltk_data_dir, quiet=True)
    except Exception as _e:
        logger.warning("NLTK download skipped for %s: %s", _pkg, _e)

if _nltk_data_dir not in nltk.data.path:
    nltk.data.path.insert(0, _nltk_data_dir)

SYMPTOMS_CACHE_TIMEOUT  = 3600
EMERGENCY_CACHE_TIMEOUT = 3600


class MedicalNLPProcessor:
    """
    Extracts medical symptoms and emergency keywords from free-text input.
    Includes Swahili and colloquial Kenyan terms.
    """

    def __init__(self) -> None:
        try:
            self.stop_words = set(stopwords.words("english"))
        except LookupError:
            logger.warning("NLTK stopwords not available — using empty set")
            self.stop_words = set()

        # Maps extracted key → list of text variations to match in user input.
        # Each key also maps to canonical_name (the human-readable text that
        # will be used for disease matching).
        self.symptom_variations: Dict[str, Dict] = {
            "fever": {
                "canonical": "fever",
                "variations": [
                    "fever", "hot body", "high temperature", "sweating", "chills",
                    "feverish", "joto", "feeling hot", "night sweats", "homa",
                    "body is hot", "ninauma joto", "temperature",
                ],
            },
            "headache": {
                "canonical": "headache",
                "variations": [
                    "headache", "head pain", "head hurting", "migraine",
                    "kichwa kuuma", "throbbing head", "pressure in head",
                    "maumivu ya kichwa",
                ],
            },
            "cough": {
                "canonical": "cough",
                "variations": [
                    "cough", "coughing", "dry cough", "wet cough", "kikohozi",
                    "chest cough", "barking cough", "cannot stop coughing",
                ],
            },
            "fatigue": {
                "canonical": "fatigue",
                "variations": [
                    "fatigue", "tired", "weakness", "exhausted", "lethargy",
                    "no energy", "body weak", "uchovu", "udhaifu", "mwili dhaifu",
                    "feeling weak", "very tired",
                ],
            },
            "vomiting": {
                "canonical": "vomiting",
                "variations": [
                    "vomit", "vomiting", "throwing up", "nausea", "sick stomach",
                    "kutapika", "feel like vomiting", "nauseated",
                ],
            },
            "diarrhea": {
                "canonical": "diarrhea",
                "variations": [
                    "diarrhea", "diarrhoea", "loose stools", "running stomach",
                    "watery stool", "kuhara", "kutharau", "stomach running",
                    "frequent stool", "watery poop", "loose stool",
                ],
            },
            "chest_pain": {
                "canonical": "chest pain",
                "variations": [
                    "chest pain", "chest discomfort", "heart pain", "tight chest",
                    "maumivu kifua", "squeezing chest", "chest tightness",
                    "chest pressure",
                ],
            },
            "difficulty_breathing": {
                "canonical": "difficulty breathing",
                "variations": [
                    "difficulty breathing", "shortness of breath", "can't breathe",
                    "breathing fast", "wheezing", "kupumua shida", "breathless",
                    "laboured breathing", "unable to breathe", "short of breath",
                    "hard to breathe", "breathing difficulty",
                ],
            },
            "joint_pain": {
                "canonical": "joint pain",
                "variations": [
                    "joint pain", "joint ache", "arthritis", "pain in joints",
                    "knees hurt", "maumivu viungo", "painful joints",
                    "aching joints",
                ],
            },
            "muscle_pain": {
                "canonical": "muscle pain",
                "variations": [
                    "muscle pain", "myalgia", "body aches", "sore muscles",
                    "whole body pain", "mwili kuuma", "maumivu mwilini",
                    "body is aching", "body pains",
                ],
            },
            "stomach_ache": {
                "canonical": "abdominal pain",
                "variations": [
                    "stomach ache", "stomach pain", "abdominal pain", "belly pain",
                    "tumbo kuuma", "cramping", "tummy hurts", "stomach cramps",
                    "tummy pain", "abdominal cramps",
                ],
            },
            "rash": {
                "canonical": "rash",
                "variations": [
                    "rash", "skin rash", "red spots", "hives",
                    "skin bumps", "upele", "spots on skin", "skin spots",
                ],
            },
            "dehydration": {
                "canonical": "dehydration",
                "variations": [
                    "dehydrated", "dry mouth", "sunken eyes", "thirsty", "dark urine",
                    "no tears", "very thirsty", "mouth dry",
                ],
            },
            "confusion": {
                "canonical": "confusion",
                "variations": [
                    "confused", "disoriented", "delirium", "not acting normal",
                    "altered mental", "not responding", "behaving strangely",
                ],
            },
            "sore_throat": {
                "canonical": "sore throat",
                "variations": [
                    "sore throat", "throat pain", "swallowing difficulty",
                    "throat swollen", "koo kuuma", "painful swallow",
                    "throat hurts",
                ],
            },
            "dizziness": {
                "canonical": "dizziness",
                "variations": [
                    "dizzy", "dizziness", "lightheaded", "spinning", "vertigo",
                    "off balance", "kizunguzungu", "feeling faint",
                ],
            },
            "numbness": {
                "canonical": "numbness",
                "variations": [
                    "numb", "numbness", "tingling", "pins and needles",
                    "loss of feeling", "feet tingling",
                ],
            },
            "swelling": {
                "canonical": "swelling",
                "variations": [
                    "swelling", "swollen", "edema", "puffy", "inflamed",
                    "kuvimba", "swollen feet", "swollen face",
                ],
            },
            "weight_loss": {
                "canonical": "weight loss",
                "variations": [
                    "weight loss", "losing weight", "getting thin",
                    "kupoteza uzito", "wasting", "very thin",
                ],
            },
            "night_sweats": {
                "canonical": "night sweats",
                "variations": [
                    "night sweats", "sweating at night", "waking up sweaty",
                    "bedsheets wet from sweat",
                ],
            },
            "jaundice": {
                "canonical": "jaundice",
                "variations": [
                    "yellow eyes", "yellow skin", "jaundice", "macho ya njano",
                    "yellowing", "eyes are yellow",
                ],
            },
            "blood_cough": {
                "canonical": "coughing blood",
                "variations": [
                    "coughing blood", "blood in sputum", "bloody cough",
                    "pink sputum", "blood when coughing",
                ],
            },
            "frequent_urination": {
                "canonical": "frequent urination",
                "variations": [
                    "frequent urination", "urinating often", "passing urine many times",
                    "wake up to pee", "mkojo mara nyingi",
                ],
            },
            "burning_urination": {
                "canonical": "burning urination",
                "variations": [
                    "burning urination", "painful urination", "urine burns",
                    "pain when urinating", "mkojo kuuma",
                ],
            },
            "stiff_neck": {
                "canonical": "stiff neck",
                "variations": [
                    "stiff neck", "neck stiffness", "cannot bend neck",
                    "shingo ngumu", "neck pain",
                ],
            },
            "convulsions": {
                "canonical": "convulsions",
                "variations": [
                    "convulsions", "seizure", "fits", "shaking uncontrollably",
                    "degedege", "epileptic attack", "jerking",
                ],
            },
            "pale_skin": {
                "canonical": "pale skin",
                "variations": [
                    "pale skin", "pallor", "pale gums", "white gums",
                    "pale conjunctiva", "inner eyelids pale",
                ],
            },
            "itching": {
                "canonical": "itching",
                "variations": [
                    "itching", "intense itch", "skin itching", "genital itching",
                    "kuwasha", "mwili kuwasha", "scratching all over",
                ],
            },
            "discharge": {
                "canonical": "discharge",
                "variations": [
                    "discharge", "genital discharge", "pus", "yellow discharge",
                    "green discharge", "smelly discharge",
                ],
            },
            "eye_pain": {
                "canonical": "eye pain",
                "variations": [
                    "eye pain", "red eyes", "eye discharge", "eye swelling",
                    "macho kuuma", "eyes red", "sticky eyes",
                ],
            },
            "ear_pain": {
                "canonical": "ear pain",
                "variations": [
                    "ear pain", "ear discharge", "hearing loss",
                    "masikio kuuma", "ears ringing", "ear ache",
                ],
            },
            "runny_nose": {
                "canonical": "runny nose",
                "variations": [
                    "runny nose", "nasal discharge", "blocked nose",
                    "pua inayotiririka", "stuffy nose",
                ],
            },
            "sneezing": {
                "canonical": "sneezing",
                "variations": [
                    "sneezing", "sneezing constantly",
                ],
            },
            "loss_appetite": {
                "canonical": "loss of appetite",
                "variations": [
                    "loss of appetite", "not eating", "no appetite",
                    "chakula hakivutii", "cannot eat", "not hungry",
                ],
            },
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_all_symptoms(self) -> list:
        key = "nlp_symptoms_v3"
        result = cache.get(key)
        if result is None:
            from .models import Symptom
            result = list(Symptom.objects.only("id", "name", "alternative_names"))
            cache.set(key, result, SYMPTOMS_CACHE_TIMEOUT)
        return result

    def _get_emergency_keywords(self) -> list:
        key = "nlp_emergency_v3"
        result = cache.get(key)
        if result is None:
            from .models import EmergencyKeyword
            result = list(
                EmergencyKeyword.objects.only("keyword", "severity", "response_message")
            )
            cache.set(key, result, EMERGENCY_CACHE_TIMEOUT)
        return result

    # ── Public API ────────────────────────────────────────────────────────────

    def preprocess(self, text: str) -> List[str]:
        """Lowercase → strip punctuation → tokenise → remove stopwords."""
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        try:
            tokens = word_tokenize(text)
        except Exception:
            tokens = text.split()
        return [t for t in tokens if t not in self.stop_words]

    def extract_symptoms(self, text: str) -> List[str]:
        """
        Extract symptom names from user input.
        Returns a deduplicated list of canonical symptom text names
        (e.g. "abdominal pain", "difficulty breathing") that directly
        match Disease.common_symptoms field values.
        """
        text_lower = text.lower()
        extracted: List[str] = []

        # Pass 1 — DB symptom records (name + alternative_names)
        try:
            for symptom in self._get_all_symptoms():
                if symptom.name.lower() in text_lower:
                    extracted.append(symptom.name.lower())
                    continue
                if symptom.alternative_names:
                    for alt in symptom.alternative_names.split(","):
                        if alt.strip().lower() in text_lower:
                            extracted.append(symptom.name.lower())
                            break
        except Exception as exc:
            logger.error("DB symptom extraction error: %s", exc)

        # Pass 2 — hardcoded Kenyan/Swahili variations → canonical text
        for sym_key, sym_data in self.symptom_variations.items():
            canonical = sym_data["canonical"]
            for var in sym_data["variations"]:
                if var in text_lower:
                    extracted.append(canonical)
                    break

        # Deduplicate preserving insertion order
        seen: set = set()
        unique: List[str] = []
        for s in extracted:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        return unique

    def detect_emergency(self, text: str) -> List[Dict]:
        """
        Check text for emergency keywords.
        Returns [{ 'keyword': str, 'severity': str, 'message': str }, ...]
        """
        text_lower = text.lower()
        emergencies: List[Dict] = []
        try:
            for kw in self._get_emergency_keywords():
                if kw.keyword.lower() in text_lower:
                    emergencies.append({
                        "keyword":  kw.keyword,
                        "severity": kw.severity,
                        "message":  kw.response_message,
                    })
        except Exception as exc:
            logger.error("Emergency detection error: %s", exc)
        return emergencies
