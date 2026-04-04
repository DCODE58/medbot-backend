"""
Management command: populate_kenya_data

Populates the database with 50+ Kenyan diseases, symptoms, first-aid
procedures, and emergency keywords.  Safe to re-run: clears then re-inserts.

Fix 13: the original loop used `diseases_raw[key]` to look up values from an
        anonymous dict that was already being iterated.  The pattern was
        fragile (duplicate key reference, easy to break on a rename).
        Rewritten as a clean `for key, (name, desc, syms) in DISEASE_DATA.items()`
        loop with no back-references to the outer dict.

Usage:
    python manage.py populate_kenya_data          # interactive confirmation
    python manage.py populate_kenya_data --force  # skip prompt (used in render.yaml)
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from chatbot.models import Disease, EmergencyKeyword, FirstAidProcedure, Symptom


class Command(BaseCommand):
    help = "Populate DB with comprehensive Kenyan medical data (50+ diseases)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip the confirmation prompt (required for automated deploys)",
        )

    def handle(self, *args, **options):
        if not options["force"]:
            self.stdout.write(self.style.WARNING(
                "This will DELETE all Disease / Symptom / FirstAidProcedure / "
                "EmergencyKeyword records and repopulate from scratch."
            ))
            if input("Continue? (y/N): ").strip().lower() != "y":
                self.stdout.write(self.style.ERROR("Aborted."))
                return

        try:
            with transaction.atomic():
                self._run()
        except Exception as exc:
            raise CommandError(f"Population failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("✅  Kenyan medical data populated!"))
        self.stdout.write(f"   • {Disease.objects.count()} diseases")
        self.stdout.write(f"   • {Symptom.objects.count()} symptoms")
        self.stdout.write(f"   • {FirstAidProcedure.objects.count()} first-aid procedures")
        self.stdout.write(f"   • {EmergencyKeyword.objects.count()} emergency keywords")

    # ─────────────────────────────────────────────────────────────────────────

    def _run(self):
        Disease.objects.all().delete()
        Symptom.objects.all().delete()
        FirstAidProcedure.objects.all().delete()
        EmergencyKeyword.objects.all().delete()

        # ── SYMPTOMS ──────────────────────────────────────────────────────────
        # Fix 13: plain dict → create; no back-reference needed
        SYMPTOM_DATA = {
            "fever":                ("fever",                         "high temperature,hot body,sweating,chills,joto,homa,feverish,night sweats"),
            "headache":             ("headache",                      "head pain,migraine,kichwa kuuma,throbbing head,maumivu ya kichwa"),
            "cough":                ("cough",                         "coughing,dry cough,wet cough,kikohozi,coughing blood,blood in sputum"),
            "diarrhea":             ("diarrhea",                      "diarrhoea,loose stools,running stomach,kuhara,watery stool,frequent stool"),
            "vomiting":             ("vomiting",                      "throwing up,nausea,sick stomach,kutapika"),
            "fatigue":              ("fatigue",                       "tiredness,weakness,exhaustion,uchovu,udhaifu,no energy,body weak"),
            "chest_pain":           ("chest pain",                    "chest discomfort,heart pain,tight chest,maumivu kifua"),
            "difficulty_breathing": ("difficulty breathing",          "shortness of breath,breathless,wheezing,kupumua shida,breathing fast"),
            "joint_pain":           ("joint pain",                    "joint ache,arthritis,knees hurt,maumivu viungo,painful joints"),
            "muscle_pain":          ("muscle pain",                   "myalgia,body aches,sore muscles,mwili kuuma,whole body pain"),
            "rash":                 ("rash",                          "skin rash,red spots,itching,hives,skin bumps,upele"),
            "abdominal_pain":       ("abdominal pain",                "stomach ache,belly pain,cramping,tumbo kuuma,stomach cramps"),
            "dehydration":          ("dehydration",                   "dry mouth,sunken eyes,thirsty,dark urine,no tears"),
            "confusion":            ("confusion",                     "disoriented,delirium,not acting normal,altered mental,not responding"),
            "burning_urination":    ("burning urination",             "pain when urinating,urine burns,mkojo kuuma,painful urination"),
            "frequent_urination":   ("frequent urination",            "passing urine often,mkojo mara nyingi,wake up to pee"),
            "blood_urine":          ("blood in urine",                "red urine,bloody urine,pink urine"),
            "lower_back_pain":      ("lower back pain",               "backache,kidney pain,spine hurts,mgongo kuuma"),
            "runny_nose":           ("runny nose",                    "nasal discharge,blocked nose,pua inayotiririka"),
            "sneezing":             ("sneezing",                      "sneezing constantly,allergy sneezing"),
            "sore_throat":          ("sore throat",                   "throat pain,difficulty swallowing,swollen throat,koo kuuma"),
            "swelling":             ("swelling",                      "swollen,edema,puffy,inflamed,kuvimba,swollen feet,swollen face"),
            "redness":              ("redness",                       "red skin,inflamed skin,hot skin"),
            "wound":                ("wound",                         "cut,injury,sore,ulcer,broken skin,open wound"),
            "hypertension_sx":      ("high blood pressure symptoms",  "severe headache,blurred vision,nose bleeding,dizziness,pounding heart"),
            "diabetes_sx":          ("high blood sugar symptoms",     "excessive thirst,frequent urination,weight loss,blurred vision,slow healing"),
            "numbness":             ("numbness",                      "tingling,pins and needles,loss of feeling,feet tingling"),
            "dizziness":            ("dizziness",                     "feeling faint,lightheaded,spinning,vertigo,kizunguzungu"),
            "jaundice":             ("jaundice",                      "yellow eyes,yellow skin,macho ya njano,yellowing"),
            "night_sweats":         ("night sweats",                  "sweating at night,waking up sweaty,bedsheets wet"),
            "weight_loss":          ("weight loss",                   "losing weight,getting thin,kupoteza uzito,wasting"),
            "blood_cough":          ("coughing blood",                "blood in sputum,bloody cough,pink sputum"),
            "stiff_neck":           ("stiff neck",                    "neck stiffness,cannot bend neck,shingo ngumu"),
            "convulsions":          ("convulsions",                   "seizure,fits,shaking,degedege,jerking,epileptic attack"),
            "pale_skin":            ("pale skin",                     "pallor,pale gums,white gums,pale conjunctiva,inner eyelids pale"),
            "itching":              ("itching",                       "intense itch,skin itching,genital itching,kuwasha,mwili kuwasha"),
            "discharge":            ("discharge",                     "genital discharge,pus,yellow discharge,green discharge,smelly discharge"),
            "eye_pain":             ("eye pain",                      "red eyes,eye discharge,sticky eyes,macho kuuma"),
            "ear_pain":             ("ear pain",                      "ear discharge,hearing loss,masikio kuuma,ear ache"),
            "genital_sores":        ("genital sores",                 "genital ulcers,sores on genitals,painless sore"),
            "heavy_bleeding":       ("heavy bleeding",                "abnormal bleeding,postpartum bleeding,heavy period,blood loss"),
            "pelvic_pain":          ("pelvic pain",                   "lower pelvic pain,painful periods,menstrual cramps,period pain"),
            "blisters":             ("skin blisters",                 "fluid-filled bumps,vesicles,water bumps,chickenpox spots"),
            "loss_appetite":        ("loss of appetite",              "not eating,no appetite,chakula hakivutii,cannot eat"),
            "fast_breathing":       ("fast breathing",                "rapid breathing,tachypnea,breathing quickly,breathing over 60 times"),
        }

        S = {}
        for key, (name, alts) in SYMPTOM_DATA.items():
            S[key] = Symptom.objects.create(name=name, alternative_names=alts)

        # ── DISEASES ──────────────────────────────────────────────────────────
        # Fix 13: each tuple is (name, description, common_symptoms).
        # Iterated directly — no fragile back-reference to an outer variable.
        DISEASE_DATA = {
            # ── Mosquito-borne ─────────────────────────────────────────────
            "malaria": (
                "Malaria",
                "Parasitic disease spread by female Anopheles mosquitoes. Leading cause of hospital "
                "admissions in Kenya. Untreated cerebral malaria can kill within 24 hours. "
                "Children under 5 and pregnant women face the highest risk.",
                "fever, headache, chills, sweating, fatigue, joint pain, vomiting, muscle pain",
            ),
            "dengue": (
                "Dengue Fever",
                "Viral infection spread by Aedes aegypti mosquitoes. Endemic in coastal Kenya. "
                "Known as break-bone fever. Severe dengue causes plasma leakage and fatal bleeding.",
                "fever, severe headache, joint pain, muscle pain, rash, pain behind eyes, fatigue, vomiting",
            ),
            "chikungunya": (
                "Chikungunya",
                "Mosquito-borne viral disease causing debilitating joint pain that may persist for months. "
                "Outbreaks documented in coastal Kenya.",
                "fever, severe joint pain, headache, rash, fatigue, muscle pain, swelling",
            ),
            "rift_valley_fever": (
                "Rift Valley Fever",
                "Viral zoonosis spread by mosquitoes and contact with livestock blood. "
                "Common in Rift Valley during rainy seasons.",
                "fever, muscle pain, weakness, dizziness, lower back pain, vomiting, headache",
            ),
            "yellow_fever": (
                "Yellow Fever",
                "Viral hemorrhagic fever spread by Aedes mosquitoes. Vaccine-preventable. "
                "Causes liver failure and hemorrhage in severe cases.",
                "fever, headache, jaundice, vomiting, abdominal pain, fatigue, muscle pain",
            ),
            "filariasis": (
                "Lymphatic Filariasis (Elephantiasis)",
                "Parasitic worm disease spread by mosquitoes. Endemic in coastal Kenya. "
                "Leads to permanent massive swelling of legs if untreated.",
                "swelling, fatigue, fever, swollen lymph nodes, skin thickening",
            ),
            "sleeping_sickness": (
                "African Sleeping Sickness (Trypanosomiasis)",
                "Parasitic disease spread by tsetse fly. Found in western Kenya. "
                "Causes progressive neurological damage, coma, and death.",
                "fever, headache, joint pain, fatigue, swollen lymph nodes, confusion, sleep disturbance",
            ),
            # ── Waterborne / Diarrheal ─────────────────────────────────────
            "cholera": (
                "Cholera",
                "Severe bacterial diarrhoeal disease from contaminated water. "
                "Can kill within hours. Common after floods and in urban slums.",
                "severe diarrhea, vomiting, dehydration, abdominal pain, muscle cramps",
            ),
            "typhoid": (
                "Typhoid Fever",
                "Bacterial infection from contaminated food and water. Can perforate intestines. "
                "Common in areas without clean piped water.",
                "fever, headache, fatigue, abdominal pain, diarrhea, loss of appetite, rash",
            ),
            "acute_diarrhea": (
                "Acute Gastroenteritis",
                "Infection of stomach and intestines. Leading killer of children under 5. "
                "Main danger is dehydration.",
                "diarrhea, vomiting, abdominal pain, dehydration, fever, nausea",
            ),
            "hepatitis_a": (
                "Hepatitis A",
                "Viral liver infection from contaminated food and water. Vaccine-preventable.",
                "jaundice, fatigue, abdominal pain, nausea, vomiting, fever, dark urine, loss of appetite",
            ),
            "hepatitis_b": (
                "Hepatitis B",
                "Viral liver infection spread through blood and sex. Can become chronic, leading to cirrhosis.",
                "jaundice, fatigue, abdominal pain, dark urine, joint pain, fever, loss of appetite",
            ),
            "hepatitis_e": (
                "Hepatitis E",
                "Waterborne viral hepatitis linked to flooding. Dangerous in pregnancy.",
                "jaundice, fatigue, nausea, vomiting, abdominal pain, fever",
            ),
            "amoebiasis": (
                "Amoebiasis",
                "Intestinal infection by Entamoeba histolytica. Can form liver abscesses.",
                "diarrhea, abdominal pain, blood in stool, fever, fatigue, weight loss",
            ),
            "giardia": (
                "Giardiasis",
                "Intestinal infection by Giardia parasite from contaminated water. "
                "Causes chronic bloating and malabsorption.",
                "diarrhea, abdominal pain, bloating, fatigue, nausea, weight loss",
            ),
            "leptospirosis": (
                "Leptospirosis",
                "Bacterial infection from water contaminated with animal urine. "
                "High risk after floods. Can cause kidney and liver failure.",
                "fever, headache, muscle pain, vomiting, jaundice, red eyes, rash",
            ),
            # ── Respiratory ────────────────────────────────────────────────
            "pneumonia": (
                "Pneumonia",
                "Lung infection causing fluid buildup. Second leading killer of children under 5.",
                "cough, difficulty breathing, chest pain, fever, fatigue, fast breathing",
            ),
            "tuberculosis": (
                "Tuberculosis (TB)",
                "Airborne bacterial lung infection. Kenya has one of the highest TB burdens in Africa. "
                "HIV co-infection very common. Requires 6 months of antibiotics.",
                "cough, coughing blood, night sweats, weight loss, fever, fatigue, chest pain",
            ),
            "upper_respiratory": (
                "Upper Respiratory Infection (Cold/Flu)",
                "Viral infection of the nose, throat, and airways. Very contagious.",
                "runny nose, sneezing, sore throat, cough, fever, headache, fatigue",
            ),
            "influenza": (
                "Influenza (Flu)",
                "Seasonal viral respiratory illness more severe than a cold.",
                "fever, cough, sore throat, muscle pain, headache, fatigue, runny nose, vomiting",
            ),
            "whooping_cough": (
                "Whooping Cough (Pertussis)",
                "Highly contagious vaccine-preventable disease. Dangerous in infants.",
                "severe cough, whooping sound, vomiting after cough, fatigue, runny nose",
            ),
            "asthma": (
                "Asthma",
                "Chronic airway inflammation. Increasing in Kenyan cities due to air pollution.",
                "difficulty breathing, wheezing, chest tightness, cough, shortness of breath",
            ),
            "covid": (
                "COVID-19",
                "Respiratory illness from SARS-CoV-2. Ranges from mild cold to fatal pneumonia.",
                "fever, cough, difficulty breathing, fatigue, headache, loss of taste, sore throat, muscle pain",
            ),
            # ── Parasitic ──────────────────────────────────────────────────
            "worms": (
                "Intestinal Worms (Helminthiasis)",
                "Parasitic worm infections from contaminated soil or food. Common in school-age children.",
                "abdominal pain, diarrhea, fatigue, weight loss, itching around anus, poor growth",
            ),
            "schistosomiasis": (
                "Schistosomiasis (Bilharzia)",
                "Parasitic worm infection from freshwater snails. Endemic in Lake Victoria basin.",
                "blood in urine, abdominal pain, diarrhea, fatigue, rash, fever, frequent urination",
            ),
            "leishmaniasis": (
                "Visceral Leishmaniasis (Kala-azar)",
                "Parasitic disease spread by sandfly bites. Fatal without treatment. "
                "Endemic in Turkana, Baringo, Isiolo, and Wajir counties.",
                "prolonged fever, weight loss, pale skin, abdominal swelling, fatigue, jaundice",
            ),
            # ── STIs & Reproductive ─────────────────────────────────────────
            "hiv": (
                "HIV/AIDS",
                "Viral infection attacking the immune system. ~1.5 million Kenyans live with HIV. "
                "Free antiretroviral therapy at government facilities.",
                "fever, fatigue, weight loss, night sweats, rash, sore throat, swollen lymph nodes",
            ),
            "gonorrhoea": (
                "Gonorrhoea",
                "Common bacterial STI with rising antibiotic resistance in Kenya.",
                "discharge, burning urination, pelvic pain, swelling of genitals",
            ),
            "syphilis": (
                "Syphilis",
                "Bacterial STI progressing through stages. Can cause heart/brain damage if untreated.",
                "genital sores, rash, fever, fatigue, sore throat, headache",
            ),
            "chlamydia": (
                "Chlamydia",
                "Most common bacterial STI — often silent. Can cause infertility if untreated.",
                "discharge, burning urination, pelvic pain, often no symptoms",
            ),
            "pid": (
                "Pelvic Inflammatory Disease (PID)",
                "Infection of female reproductive organs from untreated STIs. Major cause of infertility.",
                "pelvic pain, fever, discharge, painful periods, painful intercourse, heavy bleeding",
            ),
            # ── Skin ───────────────────────────────────────────────────────
            "ringworm": (
                "Ringworm (Tinea)",
                "Fungal skin infection causing circular patches. Very common in schools.",
                "circular rash, itching, redness, scaling, hair loss if scalp",
            ),
            "scabies": (
                "Scabies",
                "Skin infestation by mites. Highly contagious. Common in overcrowded households.",
                "itching, rash, burrow marks between fingers, redness, sores from scratching",
            ),
            "chickenpox": (
                "Chickenpox (Varicella)",
                "Highly contagious viral disease causing itchy fluid-filled blisters.",
                "fever, itching, skin blisters, fatigue, headache, rash starting on face",
            ),
            "measles": (
                "Measles",
                "Highly contagious viral disease. Outbreaks still occur in Kenya. "
                "Can cause pneumonia, blindness, and brain damage.",
                "fever, cough, runny nose, red eyes, rash starti
