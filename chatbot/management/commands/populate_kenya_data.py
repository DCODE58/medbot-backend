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
                "fever, cough, runny nose, red eyes, rash starting from face, white spots in mouth",
            ),
            "impetigo": (
                "Impetigo",
                "Contagious bacterial skin infection common in children. Honey-coloured crusted sores.",
                "skin sores, honey-coloured crusts, redness, itching, blisters",
            ),
            "cellulitis": (
                "Cellulitis",
                "Deep bacterial skin infection. Can spread rapidly to cause life-threatening sepsis.",
                "redness, swelling, warmth, pain, fever, skin blistering, red streaks",
            ),
            "skin_infection": (
                "Wound / Skin Infection",
                "Bacterial infection of wounds from cuts, bites, or sores.",
                "redness, swelling, wound, discharge, fever, pain, warmth around wound",
            ),
            # ── NCDs ───────────────────────────────────────────────────────
            "hypertension": (
                "High Blood Pressure (Hypertension)",
                "Chronic condition where blood pressure is persistently elevated. Affects 26% of Kenyan adults.",
                "severe headache, blurred vision, chest pain, difficulty breathing, nosebleed, dizziness",
            ),
            "diabetes": (
                "Diabetes Mellitus",
                "Blood sugar chronically too high. Type 2 rapidly increasing in Kenya. "
                "Can cause blindness, kidney failure, and amputations.",
                "excessive thirst, frequent urination, weight loss, fatigue, blurred vision, slow healing, numbness in feet",
            ),
            "heart_disease": (
                "Heart Disease (Coronary Artery Disease)",
                "Narrowing of arteries supplying the heart. Leading cause of death in urban Kenya.",
                "chest pain, shortness of breath, fatigue, swelling in legs, palpitations, dizziness",
            ),
            "stroke": (
                "Stroke (Cerebrovascular Accident)",
                "Brain damage from blocked or burst blood vessel. Hypertension is the main risk factor. "
                "Each minute without treatment kills 1.9 million brain cells.",
                "sudden weakness on one side, facial drooping, slurred speech, severe headache, confusion, vision loss",
            ),
            "epilepsy": (
                "Epilepsy",
                "Neurological condition causing recurrent seizures. Often linked to cerebral malaria or TB.",
                "convulsions, loss of consciousness, staring episodes, confusion after episode, jerking",
            ),
            "sickle_cell": (
                "Sickle Cell Disease",
                "Inherited blood disorder. Common in Lake Victoria basin.",
                "severe pain crises, fatigue, pale skin, jaundice, swelling in hands and feet",
            ),
            "anaemia": (
                "Anaemia",
                "Low red blood cell count. Main causes are malaria, worms, and iron deficiency. "
                "Severe in pregnant women and young children.",
                "fatigue, pale skin, dizziness, shortness of breath, fast heart rate, headache",
            ),
            # ── Eye & ENT ──────────────────────────────────────────────────
            "conjunctivitis": (
                "Conjunctivitis (Pink Eye)",
                "Inflammation of the eye conjunctiva. Highly contagious in schools.",
                "red eyes, eye discharge, itching in eyes, swollen eyelids, eye pain",
            ),
            "trachoma": (
                "Trachoma",
                "Chronic bacterial eye disease. Leading infectious cause of blindness. "
                "Endemic in arid parts of Kenya.",
                "eye discharge, red eyes, itching in eyes, eye pain, vision loss",
            ),
            "otitis_media": (
                "Ear Infection (Otitis Media)",
                "Middle ear infection, common in children under 5. Can cause permanent hearing loss.",
                "ear pain, fever, ear discharge, difficulty hearing, tugging at ear",
            ),
            "tonsillitis": (
                "Tonsillitis",
                "Inflammation of tonsils. Rheumatic fever is a serious complication if untreated.",
                "sore throat, fever, difficulty swallowing, swollen neck glands, bad breath",
            ),
            # ── Maternal & Neonatal ────────────────────────────────────────
            "eclampsia": (
                "Eclampsia / Pre-eclampsia",
                "Serious pregnancy complication. Eclampsia = seizures. "
                "Leading cause of maternal death in Kenya.",
                "severe headache, blurred vision, swollen face and hands, convulsions, abdominal pain",
            ),
            "postpartum_haemorrhage": (
                "Postpartum Haemorrhage (PPH)",
                "Excessive bleeding after childbirth. Leading cause of maternal mortality in Kenya.",
                "heavy bleeding after delivery, dizziness, weakness, rapid heart rate, pale skin",
            ),
            "mastitis": (
                "Mastitis",
                "Breast infection during breastfeeding. Can develop into abscess.",
                "breast pain, swelling, redness, fever, fatigue, warmth in breast",
            ),
            "neonatal_sepsis": (
                "Neonatal Sepsis",
                "Life-threatening blood infection in newborns. Major cause of newborn deaths.",
                "fever or low temperature in newborn, difficulty feeding, convulsions, jaundice, lethargy",
            ),
            # ── Malnutrition ───────────────────────────────────────────────
            "malnutrition": (
                "Malnutrition (Kwashiorkor / Marasmus)",
                "Severe childhood malnutrition. Common in arid regions and drought areas.",
                "swelling, weight loss, muscle wasting, fatigue, irritability, pale skin, poor growth",
            ),
            # ── Other ──────────────────────────────────────────────────────
            "meningitis": (
                "Meningitis",
                "Inflammation of brain coverings. Medical emergency. "
                "Can cause death or brain damage within hours.",
                "severe headache, fever, stiff neck, confusion, vomiting, sensitivity to light, rash",
            ),
            "uti": (
                "Urinary Tract Infection (UTI)",
                "Infection of the bladder or urethra. More common in women.",
                "burning urination, frequent urination, lower back pain, blood in urine, lower abdominal pain",
            ),
            "brucellosis": (
                "Brucellosis",
                "Bacterial zoonosis from livestock or unpasteurised dairy. Common in pastoral communities.",
                "fever, sweating, fatigue, joint pain, lower back pain, headache, muscle pain",
            ),
        }

        # Fix 13: clean loop — no ambiguous back-reference
        D = {}
        for key, (name, desc, syms) in DISEASE_DATA.items():
            D[key] = Disease.objects.create(name=name, description=desc, common_symptoms=syms)

        # ── FIRST AID PROCEDURES ──────────────────────────────────────────────
        FA = [
            (D["malaria"], "Malaria First Aid",
             "1. PARACETAMOL: Give paracetamol for fever. Do NOT give aspirin to children.\n\n"
             "2. COOL DOWN: Sponge with room-temperature water if very hot. Do not use ice.\n\n"
             "3. FLUIDS: Drink plenty of clean water, oral rehydration salts, or soup.\n\n"
             "4. REST: Lie down under an insecticide-treated mosquito net.\n\n"
             "5. TEST AND TREAT: Go to clinic for a rapid diagnostic test. "
             "Do not take anti-malarials without testing first.",
             "Severe malaria (confusion, seizures, inability to drink) can kill within 24 hours.",
             "Go to hospital IMMEDIATELY if:\n• Unconscious or confused\n• Cannot keep fluids down\n"
             "• Seizures\n• Breathing difficulty\n• Child under 5 or pregnant woman\n• Pale or yellow skin"),

            (D["dengue"], "Dengue First Aid",
             "1. COMPLETE REST: Bed rest throughout illness.\n\n"
             "2. FLUIDS: Drink 2–3 litres of ORS or clean water daily.\n\n"
             "3. PARACETAMOL ONLY: For fever and pain. "
             "NEVER give ibuprofen, aspirin, or diclofenac — they cause bleeding.\n\n"
             "4. WATCH FOR DANGER SIGNS: Most dangerous time is when fever drops on day 3–5.",
             "NEVER use aspirin or ibuprofen in dengue — they can cause fatal bleeding.",
             "Go to hospital immediately if:\n• Severe belly pain\n• Blood in vomit, stool, or urine\n"
             "• Bleeding gums or nose\n• Cold, clammy skin\n• Cannot keep fluids down"),

            (D["cholera"], "Cholera First Aid",
             "1. ORS IMMEDIATELY: Start oral rehydration salts at once in small continuous sips.\n\n"
             "2. HOME ORS: 1 litre boiled water + 6 teaspoons sugar + ½ teaspoon salt.\n\n"
             "3. VOLUME: An adult with cholera can lose 1 litre per hour — keep drinking.\n\n"
             "4. HOSPITAL: Severe cholera needs IV fluids. Get there fast.\n\n"
             "5. ISOLATE: Boil all drinking water.",
             "Cholera can kill in hours. ORS saves lives — start immediately.",
             "Go to hospital IMMEDIATELY if:\n• Cannot keep fluids down\n• Severe dehydration "
             "(sunken eyes, no urine)\n• Continuous rice-water diarrhoea\n• Confusion or extreme weakness"),

            (D["typhoid"], "Typhoid First Aid",
             "1. REST: Complete rest at home.\n\n"
             "2. FLUIDS: Boiled water, ORS, clear soups, diluted fruit juice.\n\n"
             "3. SOFT FOODS: Porridge, ugali, rice, mashed potatoes.\n\n"
             "4. HYGIENE: Strict handwashing. Separate toilet or clean with bleach.\n\n"
             "5. ANTIBIOTICS: Typhoid requires prescription antibiotics. Visit a clinic.",
             "Untreated typhoid can perforate the intestines — a surgical emergency.",
             "Go to hospital if:\n• Fever continues more than 5 days\n• Sudden severe abdominal pain\n"
             "• Confusion or delirium\n• Cannot eat or drink\n• Pale or jaundiced"),

            (D["pneumonia"], "Pneumonia First Aid",
             "1. SIT UPRIGHT: Help person sit up — do not let them lie flat.\n\n"
             "2. FRESH AIR: Open windows. Keep room warm but well-ventilated.\n\n"
             "3. WARM FLUIDS: Water, tea, or soup frequently in small amounts.\n\n"
             "4. PARACETAMOL: For fever and discomfort.\n\n"
             "5. HOSPITAL: Pneumonia needs antibiotics from a clinician.",
             "Pneumonia can be fatal in children under 5 and the elderly within days.",
             "Go to hospital immediately if:\n• Breathing faster than normal\n• Ribs visible with each breath\n"
             "• Lips or fingernails blue\n• Child cannot eat, drink, or breastfeed"),

            (D["tuberculosis"], "TB Care and Infection Control",
             "1. CLINIC IMMEDIATELY: TB requires 6 months of treatment.\n\n"
             "2. COVER COUGH: Always cough into elbow or tissue.\n\n"
             "3. NUTRITION: Eat eggs, beans, and vegetables to support immunity.\n\n"
             "4. COMPLETE TREATMENT: Never stop TB drugs early — stopping causes drug resistance.\n\n"
             "5. FAMILY TESTING: All close contacts should be screened.",
             "Drug-resistant TB develops if treatment is stopped early. Never skip doses.",
             "Go to clinic if:\n• Coughing blood\n• High fever\n• Severe weight loss\n• Night sweats lasting weeks"),

            (D["meningitis"], "Meningitis First Aid — EMERGENCY",
             "1. HOSPITAL NOW: Meningitis is a life-threatening emergency. Do not wait.\n\n"
             "2. KEEP COMFORTABLE: Keep person calm and still while travelling to hospital.\n\n"
             "3. NOTHING BY MOUTH: Do not give food or drink if confused or unconscious.\n\n"
             "4. GLASS TEST: Press a glass on any rash. If rash does not fade — rush to hospital.",
             "MENINGITIS CAN CAUSE DEATH OR BRAIN DAMAGE WITHIN HOURS.",
             "GO TO HOSPITAL IMMEDIATELY if:\n• Severe headache + fever + stiff neck\n• Confusion\n"
             "• Non-blanching rash\n• Seizures\n• Sensitivity to light"),

            (D["acute_diarrhea"], "Diarrhoea and ORS Guide",
             "1. ORS IMMEDIATELY: Start oral rehydration salts at once.\n\n"
             "2. HOME ORS: 1 litre boiled water + 6 teaspoons sugar + ½ teaspoon salt.\n\n"
             "3. FEED: Continue normal feeding — bananas, rice, porridge, ugali.\n\n"
             "4. BREASTFEED: Continue breastfeeding babies. Give ORS between feeds.\n\n"
             "5. ZINC: Zinc tablets for 10–14 days in children reduce severity.\n\n"
             "6. HANDS: Wash with soap after every bathroom visit.",
             "Dehydration is the main killer. ORS saves lives.",
             "Go to hospital if:\n• Blood in stool\n• Cannot keep fluids down\n• High fever\n• Very weak or confused"),

            (D["uti"], "UTI First Aid",
             "1. WATER: Drink 2–3 litres of clean water daily to flush bacteria.\n\n"
             "2. HYGIENE: Wipe from front to back after toilet.\n\n"
             "3. DO NOT HOLD: Urinate whenever you feel the urge.\n\n"
             "4. PARACETAMOL: For pain relief if needed.\n\n"
             "5. CLINIC: UTI needs antibiotics. Visit a clinic.",
             "Untreated UTI can spread to kidneys causing pyelonephritis.",
             "Go to hospital if:\n• Fever with chills\n• Severe back or side pain\n• Blood in urine\n• Pregnant woman"),

            (D["upper_respiratory"], "Cold / Flu First Aid",
             "1. REST: Stay home and rest.\n\n"
             "2. WARM FLUIDS: Tea with lemon and honey, warm soup, or water.\n\n"
             "3. STEAM: Inhale steam — add eucalyptus if available.\n\n"
             "4. SALT GARGLE: Gargle warm salt water for sore throat 3 times daily.\n\n"
             "5. PARACETAMOL: For fever and body aches.\n\n"
             "6. COVER COUGH: Use elbow or tissue. Wash hands frequently.",
             "Viral colds cannot be cured by antibiotics.",
             "Go to hospital if:\n• Difficulty breathing\n• Chest pain\n• Fever more than 3 days\n• Child breathing fast"),

            (D["skin_infection"], "Wound and Skin Infection First Aid",
             "1. CLEAN: Wash wound with clean water and mild soap for 5–10 minutes.\n\n"
             "2. ANTISEPTIC: Apply Dettol, betadine, or hydrogen peroxide.\n\n"
             "3. COVER: Cover with clean dry dressing. Change daily.\n\n"
             "4. ELEVATE: Raise wound if on arm or leg to reduce swelling.\n\n"
             "5. TETANUS: Wounds from metal, soil, or animals need a tetanus shot.",
             "Animal bites need immediate hospital assessment for rabies risk.",
             "Go to hospital if:\n• Redness spreading around wound\n• Pus or yellow discharge\n• Fever\n• Red streaks from wound"),

            (D["hypertension"], "High Blood Pressure Self-Care",
             "1. STAY CALM: Sit quietly and breathe deeply for 10 minutes.\n\n"
             "2. SALT: Reduce salt — no extra added to food, avoid crisps and salted fish.\n\n"
             "3. MEDICINE: Take BP medicine every day without fail. Never skip even one dose.\n\n"
             "4. TOBACCO: Stop smoking and chewing miraa.\n\n"
             "5. EXERCISE: Walk 30 minutes daily.\n\n"
             "6. CLINIC: Get blood pressure checked at least every 3 months.",
             "BP medicine must be taken for life. Stopping suddenly causes dangerous rebound.",
             "Go to hospital immediately if:\n• Severe headache that will not stop\n• Blurred vision\n• Chest pain\n• Weakness on one side"),

            (D["diabetes"], "Diabetes Self-Care",
             "1. FOOD: Regular small meals. Avoid sugar, soda, cakes, mandazi, white bread.\n\n"
             "2. EXERCISE: Walk daily — helps the body use sugar better.\n\n"
             "3. MEDICINE: Take diabetes medicines at the right time every day.\n\n"
             "4. FEET: Check feet every day for cuts or sores — diabetics heal slowly.\n\n"
             "5. MONITOR: Regular blood sugar tests at the clinic.",
             "Any foot wound in a diabetic person must be checked at a clinic the same day.",
             "Go to hospital immediately if:\n• Confusion or drowsiness\n• Fruity sweet smell on breath\n• Unconscious\n• Infected foot wound"),

            (D["stroke"], "Stroke First Aid — FAST Protocol",
             "1. FAST CHECK:\n"
             "   F — Face: Ask to smile. Is one side drooping?\n"
             "   A — Arms: Ask to raise both arms. Is one weak?\n"
             "   S — Speech: Ask to repeat a phrase. Is speech slurred?\n"
             "   T — TIME: If yes to any → CALL FOR HELP IMMEDIATELY.\n\n"
             "2. NOTHING BY MOUTH: Do not give food or drink.\n\n"
             "3. POSITION: Sit up if breathing well. Recovery position if unconscious.\n\n"
             "4. CALM: Keep person calm and still.",
             "TIME IS BRAIN. Every minute of stroke = 1.9 million brain cells dying.",
             "GO TO HOSPITAL IMMEDIATELY — treatment must begin within 4.5 hours."),

            (D["epilepsy"], "Epileptic Seizure First Aid",
             "1. CLEAR AREA: Remove hard or sharp objects from around the person.\n\n"
             "2. CUSHION HEAD: Place something soft under their head.\n\n"
             "3. DO NOT RESTRAIN: Never hold a person down during a seizure.\n\n"
             "4. TIME: Note exactly when the seizure started.\n\n"
             "5. AFTER SEIZURE: Gently roll onto side (recovery position).\n\n"
             "6. NOTHING IN MOUTH: Never put anything in mouth.",
             "You cannot swallow your tongue during a seizure. Never put anything in the mouth.",
             "Call for help if:\n• Seizure lasts more than 5 minutes\n• First ever seizure\n• Injury during seizure\n• Pregnant woman"),

            (D["anaemia"], "Anaemia Self-Care",
             "1. IRON FOODS: Red meat, liver, beans, lentils, dark leafy greens, fortified uji.\n\n"
             "2. VITAMIN C: Take with iron-rich foods to improve absorption.\n\n"
             "3. DEWORM: Treat intestinal worms which cause blood loss.\n\n"
             "4. MALARIA PREVENTION: Sleep under an insecticide-treated net.\n\n"
             "5. SUPPLEMENTS: Take iron supplements as prescribed.",
             "Severe anaemia in pregnancy is a medical emergency.",
             "Go to hospital if:\n• Pale gums and inner eyelids\n• Difficulty breathing at rest\n• Fainting\n• Pregnant woman"),

            (D["worms"], "Intestinal Worms Treatment",
             "1. MEDICINE: Albendazole 400 mg single dose. Available at clinics.\n\n"
             "2. SCHOOL DEWORMING: Children should receive deworming tablets twice yearly.\n\n"
             "3. CLEAN WATER: Drink only boiled or treated water.\n\n"
             "4. COOK FOOD WELL: Cook all meat thoroughly.\n\n"
             "5. FOOTWEAR: Wear shoes outdoors to prevent hookworm entry through skin.\n\n"
             "6. HANDWASHING: Wash hands with soap before eating and after toilet.",
             "Chronic worm infection causes severe malnutrition in children.",
             "Go to clinic if:\n• Child not growing\n• Persistent belly pain\n• Worms visible in stool\n• Signs of anaemia"),

            (D["measles"], "Measles First Aid",
             "1. ISOLATE: Keep patient away from others — spreads through the air.\n\n"
             "2. VITAMIN A: Give vitamin A supplements — reduces severity and blindness risk.\n\n"
             "3. FEVER: Paracetamol and cool sponging.\n\n"
             "4. FLUIDS: Plenty of fluids and soft food.\n\n"
             "5. EYE CARE: Wipe eyes gently with clean wet cloth.\n\n"
             "6. VACCINATE: Unvaccinated family members should receive measles vaccine immediately.",
             "Measles causes death through pneumonia and brain inflammation.",
             "Go to hospital if:\n• Breathing difficulty\n• Confusion or seizures\n• Cannot drink\n• Pus in the eye"),

            (D["hiv"], "HIV — Getting Help",
             "1. TEST: Get tested at a VCT centre. Free and confidential.\n\n"
             "2. START ART: If positive, start antiretroviral therapy (ART) immediately. ART is free.\n\n"
             "3. ADHERE: Never miss ART doses — resistance develops if you stop.\n\n"
             "4. CONDOMS: Use consistently to protect partners.\n\n"
             "5. NUTRITION: Eat a balanced diet to support immune function.\n\n"
             "6. PrEP: If negative but high-risk, ask about pre-exposure prophylaxis.",
             "HIV is manageable. People on ART in Kenya live full, long lives.",
             "Go to clinic immediately if:\n• Signs of TB or oral thrush\n• Severe weight loss\n• Persistent high fever\n• Confusion"),

            (D["eclampsia"], "Eclampsia / Pre-eclampsia — EMERGENCY",
             "1. HOSPITAL IMMEDIATELY: This is a maternal emergency. Call for help and go now.\n\n"
             "2. ROLL: If the woman is fitting, gently roll her onto her left side.\n\n"
             "3. DO NOT RESTRAIN: Clear the area around her. Do not hold her down.\n\n"
             "4. AIRWAY: After fitting stops, ensure airway is clear.\n\n"
             "5. CALM: Speak softly and reassure.",
             "ECLAMPSIA IS A LEADING CAUSE OF MATERNAL DEATH IN KENYA. Do not delay.",
             "GO TO HOSPITAL IMMEDIATELY if:\n• Pregnant woman has seizures\n• Severe headache in pregnancy\n• Very swollen face and hands"),

            (D["postpartum_haemorrhage"], "Postpartum Haemorrhage — EMERGENCY",
             "1. CALL FOR HELP: Shout for help and arrange urgent transport to hospital.\n\n"
             "2. MASSAGE UTERUS: Rub the uterus (through the belly) firmly in circles.\n\n"
             "3. BREASTFEED: Put baby to breast — releases oxytocin to help uterus contract.\n\n"
             "4. LAY FLAT: Lay woman flat and raise legs to maintain blood to vital organs.\n\n"
             "5. KEEP WARM: Cover with blanket to prevent shock.",
             "A woman can die from PPH in less than 2 hours without medical treatment.",
             "THIS IS A LIFE-THREATENING EMERGENCY — GO TO HOSPITAL NOW."),

            (D["schistosomiasis"], "Bilharzia (Schistosomiasis) Care",
             "1. CLINIC: Praziquantel is a safe, effective single-dose treatment.\n\n"
             "2. AVOID LAKE WATER: Do not swim in slow-moving freshwater in endemic areas.\n\n"
             "3. CLEAN WATER: Use piped or boiled water for bathing where possible.\n\n"
             "4. SCHOOL PROGRAMMES: Children in endemic areas should receive annual treatment.",
             "Chronic untreated bilharzia permanently damages the bladder and liver.",
             "Go to clinic if:\n• Blood in urine\n• Abdominal pain\n• Liver swelling\n• Frequent urination"),

            (D["malnutrition"], "Malnutrition First Aid",
             "1. THERAPEUTIC FEEDING: Severe malnutrition requires specialised food (Plumpy'Nut, F-75, F-100).\n\n"
             "2. DO NOT FORCE FEED: Give small amounts frequently.\n\n"
             "3. TREAT INFECTIONS: Malnutrition is complicated by infections — get full assessment.\n\n"
             "4. ORS: Treat dehydration before feeding.\n\n"
             "5. MICRONUTRIENTS: Vitamin A, zinc, and iron as prescribed.",
             "Severely malnourished children must be treated at a health facility.",
             "Go to hospital immediately for:\n• Severe wasting (visible ribs)\n• Swollen ankles with pale skin\n• Unconscious child\n• Unable to eat or drink"),
        ]

        for disease, title, steps, warning, when_help in FA:
            FirstAidProcedure.objects.create(
                disease=disease,
                title=title,
                steps=steps,
                warning_notes=warning,
                when_to_seek_help=when_help,
            )

        # ── EMERGENCY KEYWORDS ────────────────────────────────────────────────
        EK = [
            ("unconscious", "CRITICAL",
             "🚨 EMERGENCY — Person is UNCONSCIOUS.\n\nCall 999 or 112 immediately.\n\n"
             "WHILE WAITING:\n• Check if breathing — look for chest rise\n"
             "• If breathing: place on side (recovery position)\n"
             "• If NOT breathing: start CPR\n"
             "  — Push HARD and FAST on centre of chest 30 times\n"
             "  — Give 2 rescue breaths if trained\n"
             "  — Repeat until help arrives\n"
             "• Loosen any tight clothing"),

            ("not breathing", "CRITICAL",
             "🚨 EMERGENCY — Person is NOT BREATHING.\n\nCall 999/112 NOW and start CPR:\n"
             "• Lay on back on hard surface\n"
             "• Heel of hand on centre of chest\n"
             "• Push hard and fast — at least 100 times per minute\n"
             "• Give 2 rescue breaths every 30 compressions\n"
             "• Do not stop until emergency services arrive"),

            ("severe bleeding", "CRITICAL",
             "🚨 SEVERE BLEEDING.\n\nCall 999/112 immediately.\n\n"
             "STOP THE BLEEDING:\n• Press FIRMLY on wound with clean cloth\n"
             "• Do NOT remove cloth even if soaked — add more on top\n"
             "• Raise injured limb above heart level if possible\n"
             "• Keep person lying down and warm"),

            ("snake bite", "CRITICAL",
             "🚨 SNAKE BITE — Medical Emergency.\n\nCall 999/112 immediately.\n\n"
             "DO:\n• Keep person calm and completely STILL\n"
             "• Remove watches, rings, tight clothing near bite\n"
             "• Note snake colour and markings if safe\n"
             "• Get to hospital as fast as possible\n\n"
             "DO NOT:\n• Cut the wound\n• Suck out venom\n• Apply tourniquet\n• Give alcohol"),

            ("heart attack", "CRITICAL",
             "🚨 POSSIBLE HEART ATTACK.\n\nCall 999/112 immediately.\n\n"
             "WHILE WAITING:\n• Sit person comfortably — do NOT lay flat\n"
             "• Loosen tight clothing\n"
             "• If aspirin available and no allergy — give 300 mg to CHEW\n"
             "• Reassure and keep calm\n• Be ready to start CPR if needed"),

            ("choking", "CRITICAL",
             "🚨 CHOKING — Cannot Breathe.\n\nIF CONSCIOUS:\n"
             "• Give 5 firm back blows between shoulder blades\n"
             "• Then 5 abdominal thrusts (Heimlich manoeuvre)\n"
             "• Alternate until object is out\n\nIF UNCONSCIOUS:\n"
             "• Call 999/112\n• Start CPR"),

            ("drowning", "CRITICAL",
             "🚨 DROWNING.\n\nCall 999/112.\n\n"
             "• Get person out of water SAFELY (do not risk yourself)\n"
             "• Check breathing\n"
             "• If not breathing: start CPR immediately\n"
             "• Keep warm after rescue — cold water causes hypothermia"),

            ("poison", "CRITICAL",
             "🚨 POISONING.\n\nCall 999/112 or Nairobi Poison Centre: 0800 720 021\n\n"
             "• Find the container or substance if possible\n"
             "• Take it to hospital with you\n"
             "• If on skin — rinse with water for 15 minutes\n"
             "• If in eye — rinse with clean water for 15 minutes\n"
             "• If fumes — move to fresh air immediately\n"
             "• DO NOT induce vomiting unless specifically advised"),

            ("eclampsia", "CRITICAL",
             "🚨 ECLAMPSIA — Pregnant Woman Having Seizures.\n\n"
             "Maternal emergency — call 999/112 immediately.\n\n"
             "• Roll woman onto LEFT side\n"
             "• Clear area — DO NOT restrain\n"
             "• After seizure: check airway is clear\n"
             "• Get to maternity hospital NOW"),

            ("cerebral malaria", "CRITICAL",
             "🚨 CEREBRAL MALARIA — Seizures or Unconsciousness with Fever.\n\n"
             "GO TO HOSPITAL IMMEDIATELY.\n\n"
             "• Roll on side to prevent choking\n"
             "• Do NOT restrain during seizure\n"
             "• Nothing by mouth\n"
             "• This can kill in hours without IV treatment"),

            ("postpartum bleeding", "CRITICAL",
             "🚨 POSTPARTUM HAEMORRHAGE — Heavy Bleeding After Delivery.\n\n"
             "Life-threatening — act immediately.\n\n"
             "• Call for help\n"
             "• Rub uterus (belly) firmly in circles\n"
             "• Put baby to breast to stimulate contractions\n"
             "• Lay woman flat, raise legs\n"
             "• GO TO HOSPITAL NOW"),

            ("stroke", "CRITICAL",
             "🚨 POSSIBLE STROKE.\n\nFAST CHECK:\n"
             "F — Face drooping?\n"
             "A — Arm weakness?\n"
             "S — Speech slurred?\n"
             "T — TIME to call 999/112 NOW.\n\nEvery minute matters — go to hospital immediately."),

            ("seizure", "URGENT",
             "⚠️ SEIZURE.\n\nDO:\n• Move hard objects away\n• Cushion head with something soft\n"
             "• Time the seizure\n• Roll onto side after jerking stops\n• Stay with the person\n\n"
             "DO NOT:\n• Restrain the person\n• Put anything in the mouth\n\n"
             "Call 999/112 if: seizure lasts > 5 minutes, no recovery, first ever seizure, or injury occurs"),

            ("burn", "URGENT",
             "⚠️ BURN.\n\n"
             "• Cool burn with COOL (not cold/ice) running water for 20 minutes\n"
             "• Remove jewellery and watches before swelling starts\n"
             "• DO NOT apply toothpaste, butter, egg, or oil\n"
             "• Cover loosely with clean cling wrap or cloth\n\n"
             "Go to hospital if burn is on face, hands, feet, genitals, or larger than palm of hand"),

            ("fainting", "URGENT",
             "⚠️ FAINTING.\n\n"
             "• Lay person flat and raise legs above heart level\n"
             "• Loosen tight clothing\n"
             "• Ensure fresh air\n"
             "• Do NOT let them sit or stand up too quickly\n\n"
             "Call for help if not fully recovered within 1 minute"),

            ("convulsions", "URGENT",
             "⚠️ CONVULSIONS.\n\n"
             "• Clear area around person\n• Cushion head\n• DO NOT hold down\n"
             "• Roll onto side after jerking stops\n• Time the duration\n\n"
             "Call 999/112 if lasting more than 5 minutes"),

            ("bleeding", "URGENT",
             "⚠️ BLEEDING.\n\n"
             "• Apply firm pressure with clean cloth\n"
             "• Raise injured area if possible\n"
             "• Do not remove cloth — add more if it soaks through\n\n"
             "Call 999/112 if bleeding is severe, pulsing, or will not stop"),

            ("chest pain", "URGENT",
             "⚠️ CHEST PAIN.\n\n"
             "Possible heart attack — especially with sweating, arm pain, or jaw pain.\n\n"
             "• Have person sit comfortably and rest\n"
             "• Loosen clothing\n"
             "• If aspirin available and no allergy — give 300 mg to chew\n\n"
             "Call 999/112 if pain is severe, spreading, or person feels unwell"),

            # Common misspellings / variant phrases
            ("unconcious", "CRITICAL",
             "🚨 Unconscious person. Call 999/112 NOW.\n"
             "Check breathing. If breathing, recovery position. If not — start CPR."),

            ("not waking", "CRITICAL",
             "🚨 Person cannot be woken. Call 999/112 immediately.\n"
             "Check breathing and start CPR if needed."),

            ("pregnancy emergency", "CRITICAL",
             "🚨 PREGNANCY EMERGENCY.\n\nCall 999/112 immediately.\n\n"
             "• Keep woman calm and lying on her LEFT side\n"
             "• Note any bleeding, seizures, or loss of consciousness\n"
             "• Do not give food or drink\n"
             "• Get to the nearest maternity hospital NOW"),
        ]

        for keyword, severity, response in EK:
            EmergencyKeyword.objects.get_or_create(
                keyword=keyword,
                defaults={"severity": severity, "response_message": response},
            )
