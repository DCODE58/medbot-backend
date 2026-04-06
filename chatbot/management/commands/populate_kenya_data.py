"""
Management command: populate_kenya_data

Populates the database with 50+ Kenyan diseases, symptoms, first-aid
procedures, and emergency keywords.  Safe to re-run: clears then re-inserts.

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
            "muscle_pain":          ("muscle pain",                   "myalgia,body aches,sore muscles,mwili kuuma,whole body pain,maumivu mwilini"),
            "rash":                 ("rash",                          "skin rash,red spots,itching,hives,skin bumps,upele"),
            "abdominal_pain":       ("abdominal pain",                "stomach ache,belly pain,cramping,tumbo kuuma,stomach cramps,stomach pain"),
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
            "eye_pain":             ("eye pain",                      "red eyes,eye discharge,eye swelling,macho kuuma,eyes red,sticky eyes"),
            "ear_pain":             ("ear pain",                      "ear discharge,hearing loss,masikio kuuma,ears ringing,ear ache"),
            "loss_appetite":        ("loss of appetite",              "not eating,no appetite,chakula hakivutii,cannot eat"),
            "fast_breathing":       ("fast breathing",                "rapid breathing,tachypnea,breathing quickly,breathing over 60 times"),
            "stomach_ache":         ("stomach ache",                  "tummy hurts,belly ache,tumbo maumivu,indigestion"),
        }

        S = {}
        for key, (name, alts) in SYMPTOM_DATA.items():
            S[key] = Symptom.objects.create(name=name, alternative_names=alts)

        # ── DISEASES ──────────────────────────────────────────────────────────
        # Each tuple: (display_name, description, common_symptoms_text)
        DISEASE_DATA = {
            # ── Mosquito-borne ────────────────────────────────────────────────
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
            # ── Waterborne / Diarrheal ────────────────────────────────────────
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
            # ── Respiratory ───────────────────────────────────────────────────
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
            # ── Parasitic ─────────────────────────────────────────────────────
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
            # ── STIs & Reproductive ───────────────────────────────────────────
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
                "discharge, burning urination, pelvic pain",
            ),
            "pid": (
                "Pelvic Inflammatory Disease (PID)",
                "Infection of female reproductive organs from untreated STIs. Major cause of infertility.",
                "pelvic pain, fever, discharge, painful periods, painful intercourse, heavy bleeding",
            ),
            # ── Skin ──────────────────────────────────────────────────────────
            "ringworm": (
                "Ringworm (Tinea)",
                "Fungal skin infection causing circular patches. Very common in schools.",
                "circular rash, itching, redness, scaling, hair loss",
            ),
            "scabies": (
                "Scabies",
                "Skin infestation by mites. Highly contagious. Common in overcrowded households.",
                "itching, rash, redness, sores from scratching",
            ),
            "chickenpox": (
                "Chickenpox (Varicella)",
                "Highly contagious viral disease causing itchy fluid-filled blisters.",
                "fever, itching, skin blisters, fatigue, headache, rash",
            ),
            "measles": (
                "Measles",
                "Highly contagious viral disease. Outbreaks still occur in Kenya. "
                "Can cause pneumonia, blindness, and brain damage.",
                "fever, cough, runny nose, red eyes, rash, fatigue, headache",
            ),
            "impetigo": (
                "Impetigo",
                "Highly contagious bacterial skin infection. Common in children.",
                "skin sores, blisters, redness, crusting, itching",
            ),
            # ── Non-communicable ─────────────────────────────────────────────
            "hypertension": (
                "Hypertension (High Blood Pressure)",
                "Silent killer affecting 1 in 3 Kenyan adults. Major risk factor for stroke and heart attack.",
                "severe headache, blurred vision, nosebleed, dizziness, chest pain, shortness of breath",
            ),
            "diabetes_type2": (
                "Type 2 Diabetes",
                "Chronic metabolic disorder. Rapidly increasing in Kenya due to urbanisation and diet changes.",
                "excessive thirst, frequent urination, weight loss, fatigue, blurred vision, slow-healing wounds, numbness in feet",
            ),
            "heart_attack": (
                "Heart Attack (Myocardial Infarction)",
                "Blocked coronary artery causing heart muscle death. Requires emergency care.",
                "chest pain, chest pressure, left arm pain, shortness of breath, sweating, nausea, dizziness",
            ),
            "stroke": (
                "Stroke",
                "Brain injury from blocked or ruptured blood vessel. Leading cause of disability in Kenya.",
                "sudden face drooping, arm weakness, speech difficulty, severe headache, confusion, vision loss",
            ),
            "anaemia": (
                "Anaemia",
                "Low red blood cell count. Very common in Kenya, especially in women and children. "
                "Often caused by iron deficiency, malaria, or worm infections.",
                "fatigue, pale skin, pale gums, shortness of breath, dizziness, cold hands, headache",
            ),
            "malnutrition": (
                "Malnutrition",
                "Deficiency of essential nutrients. Common in arid and semi-arid counties.",
                "weight loss, fatigue, pale skin, swelling of feet and face, poor growth, weakness",
            ),
            # ── Neurological / Other ─────────────────────────────────────────
            "meningitis": (
                "Meningitis",
                "Life-threatening inflammation of brain membranes. Bacterial meningitis can kill in 24 hours.",
                "severe headache, stiff neck, fever, light sensitivity, vomiting, confusion, convulsions, rash",
            ),
            "epilepsy": (
                "Epilepsy",
                "Chronic neurological condition causing recurrent seizures. Highly stigmatised in Kenya.",
                "convulsions, loss of consciousness, muscle jerking, confusion after episode, fatigue",
            ),
            # ── Eye & ENT ────────────────────────────────────────────────────
            "conjunctivitis": (
                "Conjunctivitis (Pink Eye)",
                "Highly contagious eye infection. Can be viral, bacterial, or allergic.",
                "red eyes, eye discharge, eye pain, itching, tearing, swollen eyelids",
            ),
            "trachoma": (
                "Trachoma",
                "Bacterial eye infection — leading infectious cause of blindness globally. "
                "Endemic in arid parts of Kenya.",
                "eye discharge, red eyes, eye pain, eyelid scarring, light sensitivity",
            ),
            "otitis_media": (
                "Ear Infection (Otitis Media)",
                "Middle ear infection common in children. Can lead to permanent hearing loss if untreated.",
                "ear pain, fever, hearing loss, discharge from ear, irritability, headache",
            ),
            # ── Urinary ──────────────────────────────────────────────────────
            "uti": (
                "Urinary Tract Infection (UTI)",
                "Bacterial infection of the bladder or kidneys. Very common in women.",
                "burning urination, frequent urination, lower back pain, cloudy urine, fever, pelvic pain",
            ),
            "kidney_stones": (
                "Kidney Stones",
                "Mineral deposits in the kidneys causing intense pain when passing.",
                "severe back pain, side pain, painful urination, blood in urine, nausea, vomiting, fever",
            ),
            # ── Maternal/Child Health ─────────────────────────────────────────
            "malaria_pregnancy": (
                "Malaria in Pregnancy",
                "High-risk form of malaria. Can cause maternal anaemia, miscarriage, and low birth weight.",
                "fever, chills, headache, fatigue, anaemia, abdominal pain, vomiting",
            ),
            "pre_eclampsia": (
                "Pre-eclampsia",
                "Dangerous blood pressure condition in pregnancy. Requires immediate medical attention.",
                "severe headache, blurred vision, swelling of face and hands, upper abdominal pain, vomiting",
            ),
            # ── Injuries / Wounds ─────────────────────────────────────────────
            "snake_bite": (
                "Snake Bite",
                "Medical emergency in rural Kenya. Over 4,000 bites per year. Requires antivenin.",
                "bite wound, swelling, pain, vomiting, difficulty breathing, bleeding, confusion",
            ),
            "wound_infection": (
                "Wound Infection / Sepsis",
                "Bacterial infection of a wound that can progress to life-threatening sepsis.",
                "wound redness, wound swelling, pus, fever, warmth around wound, pain, red streaks",
            ),
            "burns": (
                "Burns",
                "Common injury, especially from open cooking fires in rural Kenya.",
                "skin redness, blistering, pain, swelling, charred skin in severe cases",
            ),
        }

        # ── Create Disease objects and link Symptoms ───────────────────────────
        D = {}
        for key, (name, desc, syms) in DISEASE_DATA.items():
            d = Disease.objects.create(
                name=name,
                description=desc,
                common_symptoms=syms,
            )
            D[key] = d

            # Link Symptom objects to disease via M2M
            syms_lower = [s.strip().lower() for s in syms.split(",")]
            for sym_key, sym_obj in S.items():
                # Match by canonical name or any alternative
                if sym_obj.name.lower() in syms_lower:
                    d.symptoms.add(sym_obj)
                    continue
                for alt in sym_obj.alternative_names.split(","):
                    if alt.strip().lower() in syms_lower:
                        d.symptoms.add(sym_obj)
                        break

        # ── FIRST-AID PROCEDURES ──────────────────────────────────────────────
        FA_DATA = [
            ("malaria", "Malaria First Aid",
             "1. Rest the patient in a cool, shaded area.\n"
             "2. Give paracetamol (NOT aspirin or ibuprofen) to reduce fever — follow dosing on pack.\n"
             "3. Ensure adequate oral fluids — water, oral rehydration solution (ORS), or juice.\n"
             "4. Use a damp cloth on the forehead to manage high fever.\n"
             "5. Seek diagnostic testing (RDT or blood smear) at the nearest health facility IMMEDIATELY.\n"
             "6. Do NOT self-treat with antimalarials without a confirmed diagnosis.\n"
             "7. Complete the full course of prescribed antimalarials — even if the patient feels better.",
             "Do NOT give aspirin or ibuprofen to children with fever — risk of Reye's syndrome. "
             "Do NOT delay going to hospital — cerebral malaria can be fatal within hours.",
             "Go to hospital immediately if: confusion, seizures, very high fever, inability to drink, "
             "repeated vomiting, laboured breathing, or pallor (pale gums/skin)."),

            ("dengue", "Dengue Fever First Aid",
             "1. Rest completely — avoid any strenuous activity.\n"
             "2. Drink plenty of fluids: water, ORS, coconut water, or fresh juice.\n"
             "3. Give paracetamol for fever and pain — follow dosing instructions.\n"
             "4. Use a damp cloth or fan to cool the patient.\n"
             "5. Monitor for warning signs of severe dengue (see below).\n"
             "6. Mosquito net rest prevents infecting others via mosquitoes.",
             "NEVER give aspirin or ibuprofen — they increase bleeding risk significantly. "
             "There is no specific antiviral treatment; supportive care is essential.",
             "Go to hospital immediately if: severe abdominal pain, persistent vomiting, bleeding gums or nose, "
             "blood in urine or stool, rapid breathing, sudden drop in temperature, or extreme fatigue."),

            ("cholera", "Cholera Emergency First Aid",
             "1. Start Oral Rehydration Therapy (ORT) IMMEDIATELY — this is the most important step.\n"
             "2. Make ORS: dissolve 1 sachet (or 1 teaspoon salt + 8 teaspoons sugar) in 1 litre clean water.\n"
             "3. Give small, frequent sips — 200–400 ml after each loose stool.\n"
             "4. Continue breastfeeding infants.\n"
             "5. Transport patient to nearest health facility urgently.\n"
             "6. Isolate patient's faeces — wash hands with soap thoroughly.",
             "Cholera can kill by dehydration within hours. Do NOT wait to start ORT while arranging transport. "
             "Avoid home remedies that delay treatment.",
             "Transport to hospital IMMEDIATELY. IV fluids are needed for severe cases. "
             "Children and elderly are most at risk of rapid deterioration."),

            ("typhoid", "Typhoid Fever First Aid",
             "1. Keep the patient at strict bed rest.\n"
             "2. Give plenty of cool, clean fluids to prevent dehydration.\n"
             "3. Administer paracetamol for fever control.\n"
             "4. Feed soft, easily digestible foods — avoid raw vegetables.\n"
             "5. Strict handwashing with soap for patient and carers.\n"
             "6. Seek medical care for prescription antibiotics — essential for cure.",
             "Typhoid can cause intestinal perforation — a surgical emergency. "
             "Never give anti-diarrhoeal drugs. Do not stop antibiotics early.",
             "Go to hospital immediately if: extreme abdominal pain and rigidity (perforation), "
             "loss of consciousness, very high fever, difficulty breathing, or no improvement after 3 days of antibiotics."),

            ("pneumonia", "Pneumonia First Aid",
             "1. Keep the patient upright or semi-sitting — this eases breathing.\n"
             "2. Ensure the room is well-ventilated.\n"
             "3. Keep the patient warm but not overheated.\n"
             "4. Encourage slow, deep breaths.\n"
             "5. Give paracetamol for fever.\n"
             "6. Ensure adequate hydration with small, frequent sips.\n"
             "7. SEEK MEDICAL CARE URGENTLY — pneumonia requires antibiotics.",
             "Do not give cough suppressants — coughing helps clear the lungs. "
             "Antibiotics must be prescribed by a health worker.",
             "Go to hospital immediately if: breathing rate over 50/min in adults or 60/min in infants, "
             "blue lips or fingernails (cyanosis), confusion, inability to drink, or chest in-drawing."),

            ("tuberculosis", "Tuberculosis (TB) First Aid & Support",
             "1. Encourage the patient to seek TB testing at the nearest health facility — it is FREE in Kenya.\n"
             "2. Isolate the patient in a well-ventilated room — open windows, avoid crowded spaces.\n"
             "3. Patient should wear a surgical mask when around others.\n"
             "4. Provide nutritious meals — TB causes weight loss and weakens immunity.\n"
             "5. Support the patient to complete the FULL 6-month treatment course.\n"
             "6. All household contacts should get tested.",
             "TB treatment is free in all Kenyan public health facilities. "
             "Stopping treatment early causes drug-resistant TB which is much harder to treat. "
             "Do NOT give herbal remedies as a substitute for prescribed treatment.",
             "Seek medical care if: coughing blood, extreme weight loss, night sweats, or fever lasting more than 3 weeks."),

            ("meningitis", "Meningitis Emergency First Aid",
             "1. CALL FOR EMERGENCY TRANSPORT IMMEDIATELY — meningitis is a medical emergency.\n"
             "2. Keep the patient still and calm — avoid bright lights and noise.\n"
             "3. If conscious, give paracetamol for fever.\n"
             "4. Monitor breathing and consciousness at all times.\n"
             "5. Place unconscious patient in recovery position.\n"
             "6. Do NOT give anything by mouth if the patient is vomiting or unconscious.",
             "Bacterial meningitis can cause death within 24 hours or permanent brain damage. "
             "Do NOT delay seeking emergency medical care under any circumstances.",
             "This is a MEDICAL EMERGENCY. Go to hospital by the fastest means available. "
             "Dial 999 or 112. Antibiotics must be given by IV in hospital — there is no effective home treatment."),

            ("upper_respiratory", "Upper Respiratory Infection (Cold/Flu) First Aid",
             "1. Rest at home — do not go to work or school while symptomatic.\n"
             "2. Drink plenty of warm fluids: water, warm water with lemon and honey, or soup.\n"
             "3. Gargle with warm salt water for sore throat.\n"
             "4. Use steam inhalation for nasal congestion.\n"
             "5. Paracetamol or ibuprofen for fever and pain — follow dosing.\n"
             "6. Wash hands frequently to prevent spread.",
             "Antibiotics do NOT work against viral infections — do not pressure doctors for them. "
             "Do not give aspirin to children under 16.",
             "Seek medical care if: fever above 39°C, breathing difficulty, symptoms worsen after 7 days, "
             "chest pain, or confusion."),

            ("influenza", "Influenza First Aid",
             "1. Rest completely — flu requires more rest than a common cold.\n"
             "2. Drink plenty of fluids to prevent dehydration.\n"
             "3. Paracetamol or ibuprofen for fever and body aches.\n"
             "4. Stay home to avoid spreading influenza.\n"
             "5. Eat easily digestible foods.\n"
             "6. Consider annual flu vaccination for prevention.",
             "Never give aspirin to children — Reye's syndrome risk. "
             "High-risk groups (elderly, pregnant, diabetic) should seek medical care promptly.",
             "Seek medical care if: persistent high fever, breathing difficulty, chest pain, "
             "confusion, or no improvement after 5 days."),

            ("asthma", "Asthma Attack First Aid",
             "1. Sit the patient upright — do NOT lay them down.\n"
             "2. Give reliever inhaler (salbutamol/Ventolin) — 4–6 puffs via spacer or direct.\n"
             "3. Reassure the patient — keep them calm.\n"
             "4. Remove from the trigger (smoke, dust, pollen) if present.\n"
             "5. If no improvement in 5–10 minutes, give another 4–6 puffs.\n"
             "6. If no improvement after 3 rounds — call emergency services.",
             "NEVER give a sedative to an asthmatic patient. "
             "Do not leave the patient alone during an attack.",
             "Call 999 or 112 if: lips or fingernails turn blue, patient cannot speak full sentences, "
             "reliever inhaler has no effect, or patient is exhausted from breathing effort."),

            ("heart_attack", "Heart Attack Emergency First Aid",
             "1. CALL 999 OR 112 IMMEDIATELY.\n"
             "2. Sit the patient in a comfortable position — semi-reclined, not flat.\n"
             "3. Loosen tight clothing around the neck and chest.\n"
             "4. If the patient is not allergic to aspirin and can swallow — give 300mg aspirin to chew slowly.\n"
             "5. Keep the patient calm and still.\n"
             "6. If the patient becomes unconscious and stops breathing — start CPR.\n"
             "7. Do NOT leave the patient alone.",
             "This is a LIFE-THREATENING EMERGENCY. Every minute of delay increases heart damage. "
             "Do NOT give aspirin if the patient is allergic or has bleeding disorders.",
             "This is a MEDICAL EMERGENCY. Call emergency services and go to hospital by the fastest means. "
             "Do not drive yourself to hospital during a heart attack."),

            ("stroke", "Stroke Emergency First Aid — FAST",
             "1. Use FAST test: Face drooping, Arm weakness, Speech difficulty, Time to call 999/112.\n"
             "2. CALL 999 OR 112 IMMEDIATELY — note the exact time symptoms started.\n"
             "3. Keep the patient calm and still — do NOT give food or water.\n"
             "4. Lay the patient on their side if unconscious (recovery position).\n"
             "5. Loosen tight clothing.\n"
             "6. Do NOT give aspirin unless instructed by emergency services.",
             "Time is CRITICAL — clot-busting treatment must be given within 4.5 hours of onset. "
             "Do NOT leave the patient alone. Do NOT give food or water — swallowing reflex may be impaired.",
             "THIS IS A MEDICAL EMERGENCY. Call 999 or 112 immediately. "
             "The faster a stroke is treated, the less brain damage occurs."),

            ("diabetes_type2", "Diabetic Emergency (Low Blood Sugar) First Aid",
             "1. If conscious and able to swallow: give 3–4 glucose tablets, OR 150ml fruit juice, OR "
             "3 teaspoons of sugar dissolved in water.\n"
             "2. Wait 15 minutes and reassess.\n"
             "3. If improved, give a starchy snack: banana, bread, or ugali.\n"
             "4. If not improved after 15 minutes, give another sugary drink and seek emergency care.\n"
             "5. If unconscious: DO NOT give anything by mouth — call emergency services immediately.\n"
             "6. Place unconscious patient in recovery position.",
             "Do NOT give sugar to a diabetic patient with HIGH blood sugar — this requires hospital treatment. "
             "If unsure, call emergency services.",
             "Seek emergency care if: patient loses consciousness, seizures occur, or blood sugar is unresponsive "
             "to treatment. High blood sugar (DKA) also requires emergency care: fruity breath, deep rapid breathing."),

            ("hypertension", "Hypertension Crisis First Aid",
             "1. Keep the patient calm — stress raises blood pressure further.\n"
             "2. Seat the patient comfortably — do NOT lay flat.\n"
             "3. If the patient takes blood pressure medication, give their prescribed dose if missed.\n"
             "4. Loosen tight clothing.\n"
             "5. Take blood pressure readings every 5–10 minutes if a monitor is available.\n"
             "6. Seek medical care for any reading above 180/120 mmHg.",
             "Do NOT give others' blood pressure medications. "
             "Hypertension is a silent disease — regular monitoring is essential even without symptoms.",
             "Seek emergency care IMMEDIATELY if: severe headache, chest pain, vision changes, "
             "confusion, or signs of stroke (face drooping, arm weakness, speech difficulty)."),

            ("anaemia", "Anaemia First Aid & Management",
             "1. Encourage iron-rich foods: dark leafy greens (spinach, sukuma wiki), beans, meat, fish.\n"
             "2. Take iron supplements as prescribed — on an empty stomach if tolerated.\n"
             "3. Pair iron-rich foods with Vitamin C (orange, tomato) to enhance absorption.\n"
             "4. Treat the underlying cause (malaria, worms, heavy periods).\n"
             "5. Deworm with albendazole (available at health facilities).\n"
             "6. Seek medical care for a blood test to confirm anaemia and identify cause.",
             "Do NOT take iron supplements without a diagnosis — excess iron is toxic. "
             "Avoid drinking tea or milk with iron-rich meals — these reduce iron absorption.",
             "Seek urgent care if: extreme fatigue, fainting, severe pallor, chest pain, or "
             "shortness of breath at rest."),

            ("uti", "UTI First Aid",
             "1. Drink plenty of water — at least 2–3 litres per day to flush bacteria.\n"
             "2. Urinate frequently — do NOT hold urine.\n"
             "3. Paracetamol or ibuprofen for pain relief.\n"
             "4. Apply a warm compress to the lower abdomen for pain.\n"
             "5. Avoid caffeine, alcohol, and spicy foods which irritate the bladder.\n"
             "6. Seek medical care for antibiotic prescription — essential for cure.",
             "Antibiotics are required — UTIs do not clear on their own. "
             "Untreated UTIs can progress to kidney infection (pyelonephritis).",
             "Seek urgent care if: fever and back pain (kidney involvement), blood in urine, "
             "symptoms in pregnancy, or symptoms persist after 3 days of antibiotics."),

            ("wound_infection", "Wound Infection First Aid",
             "1. Wash hands thoroughly before touching the wound.\n"
             "2. Clean the wound with clean running water and gentle soap.\n"
             "3. Apply an antiseptic (iodine or chlorhexidine) to the wound.\n"
             "4. Cover with a clean, sterile dressing.\n"
             "5. Change dressings daily and keep the wound dry.\n"
             "6. Elevate the affected limb if swollen.\n"
             "7. Seek medical care if signs of infection develop.",
             "Do NOT use dirty cloths to cover wounds. "
             "Do NOT remove embedded objects — this can cause severe bleeding.",
             "Seek medical care IMMEDIATELY if: red streaks spreading from wound (septicaemia), "
             "fever, pus discharge, wound won't stop bleeding, or patient has not had tetanus vaccine recently."),

            ("snake_bite", "Snake Bite Emergency First Aid",
             "1. CALL 999 OR 112 IMMEDIATELY.\n"
             "2. Keep the patient still and calm — movement spreads venom faster.\n"
             "3. Immobilise the bitten limb below the level of the heart.\n"
             "4. Remove rings, watches, or tight clothing near the bite.\n"
             "5. Mark the edge of any swelling with a pen and note the time.\n"
             "6. Transport to hospital as quickly as possible.",
             "Do NOT cut the bite, suck out venom, apply tourniquet, or use ice. "
             "Do NOT give alcohol. These actions cause MORE harm. "
             "Try to remember the snake's appearance for antivenin selection.",
             "This is a MEDICAL EMERGENCY. Antivenin must be given in hospital. "
             "Time from bite to treatment is critical."),

            ("burns", "Burns First Aid",
             "1. STOP the burning: remove from heat source. Remove clothing and jewellery unless stuck to skin.\n"
             "2. COOL the burn: run cool (NOT cold or iced) water over the burn for 20 minutes.\n"
             "3. COVER with a clean, non-fluffy material (cling wrap or a clean plastic bag is ideal).\n"
             "4. Do NOT apply toothpaste, butter, or oil — these cause infection and retain heat.\n"
             "5. Give paracetamol for pain.\n"
             "6. Raise the affected area if possible.",
             "NEVER use ice, iced water, butter, toothpaste, or raw egg on burns. "
             "Do not burst blisters — this increases infection risk.",
             "Seek emergency care for: burns on face, hands, feet, genitals, or joints; "
             "burns larger than the patient's palm; deep white/black burns; chemical or electrical burns; "
             "burns in children under 5 or adults over 60."),

            ("conjunctivitis", "Conjunctivitis (Pink Eye) First Aid",
             "1. Wash hands before and after touching the eyes.\n"
             "2. Clean eye discharge with a clean, warm, damp cloth — wipe from inner to outer corner.\n"
             "3. Use a separate cloth for each eye.\n"
             "4. Do NOT share towels, pillows, or eye drops.\n"
             "5. Remove contact lenses until infection clears.\n"
             "6. Seek medical care for antibiotic drops (bacterial) or antiviral treatment (viral).",
             "Conjunctivitis is highly contagious. Wash hands frequently. "
             "Do not touch or rub eyes.",
             "Seek medical care if: severe eye pain, vision loss, sensitivity to light, "
             "intense redness, or symptoms not improving after 3 days."),

            ("malaria_pregnancy", "Malaria in Pregnancy — Emergency First Aid",
             "1. Seek medical care IMMEDIATELY — malaria in pregnancy is an emergency.\n"
             "2. Give paracetamol to reduce fever while arranging transport.\n"
             "3. Ensure adequate hydration.\n"
             "4. Sleep under an insecticide-treated bed net every night.\n"
             "5. Take Intermittent Preventive Treatment (IPTp) as advised at antenatal clinic.",
             "Do NOT self-medicate with antimalarials during pregnancy without medical supervision. "
             "Some antimalarials are dangerous to the unborn baby.",
             "GO TO HOSPITAL IMMEDIATELY. Malaria in pregnancy can cause miscarriage, premature birth, "
             "severe anaemia, and maternal death."),

            ("pre_eclampsia", "Pre-eclampsia Emergency First Aid",
             "1. CALL 999 OR 112 IMMEDIATELY — pre-eclampsia is a medical emergency.\n"
             "2. Keep the patient calm and at rest in a quiet, darkened room.\n"
             "3. Lay on the LEFT side if possible.\n"
             "4. Do NOT give any medications without medical instruction.\n"
             "5. Monitor for seizures (eclampsia) — see below.",
             "Pre-eclampsia can progress to eclampsia (seizures) and maternal/fetal death without hospital treatment.",
             "GO TO HOSPITAL IMMEDIATELY. Pre-eclampsia only resolves after delivery — "
             "only hospital management can prevent serious harm."),

            ("chickenpox", "Chickenpox First Aid",
             "1. Keep nails short and clean — discourage scratching to prevent scarring and infection.\n"
             "2. Apply calamine lotion or antihistamine cream to relieve itching.\n"
             "3. Give paracetamol for fever — NOT aspirin or ibuprofen.\n"
             "4. Cool baths with baking soda help relieve itching.\n"
             "5. Wear loose, cotton clothing.\n"
             "6. Keep child home from school until all blisters have crusted over.",
             "Do NOT give aspirin — risk of Reye's syndrome. "
             "Chickenpox is highly contagious from 2 days before the rash until all blisters crust.",
             "Seek medical care if: rash near eyes, rash in immunocompromised patient, "
             "severe headache or stiff neck, high fever, difficulty breathing, or infected blisters."),

            ("acute_diarrhea", "Acute Gastroenteritis / Diarrhea First Aid",
             "1. Start Oral Rehydration Solution (ORS) IMMEDIATELY.\n"
             "2. Adults: drink 200–400 ml ORS after each loose stool.\n"
             "3. Children: give 50–100 ml ORS per kg body weight over 4 hours.\n"
             "4. Continue breastfeeding infants.\n"
             "5. Give zinc supplements to children 6 months–5 years for 10–14 days.\n"
             "6. Wash hands with soap after using toilet and before eating.",
             "Do NOT give anti-diarrhoeal drugs to children — they can be dangerous. "
             "If homemade ORS: 1 level teaspoon salt + 8 level teaspoons sugar per 1 litre clean water.",
             "Seek medical care if: blood or mucus in stool, no urine in 6+ hours (child) or 8+ hours (adult), "
             "sunken eyes, dry mouth, persistent vomiting, or fever above 38.5°C."),

            ("hiv", "HIV First Aid & Support",
             "1. If potential recent exposure (within 72 hours): seek PEP (Post-Exposure Prophylaxis) "
             "at any government hospital IMMEDIATELY.\n"
             "2. Get tested — HIV testing is FREE and confidential at all public facilities.\n"
             "3. If positive: start ART (antiretroviral therapy) — it is FREE in Kenya and saves lives.\n"
             "4. Practice safe sex to protect partners.\n"
             "5. Eat nutritious meals to support the immune system.\n"
             "6. Attend all clinic appointments and take medication daily.",
             "There is NO cure for HIV, but ART controls the virus completely. "
             "People on ART live full, long lives and cannot transmit the virus to partners.",
             "Seek medical care for any opportunistic infections: persistent fever, weight loss, "
             "chronic cough, thrush, or skin lesions."),

            ("epilepsy", "Seizure / Epilepsy First Aid",
             "1. Stay calm — most seizures stop on their own within 1–3 minutes.\n"
             "2. Ease the person to the ground — protect the head with a folded cloth.\n"
             "3. Clear the area of hard or sharp objects.\n"
             "4. Lay the person on their side (recovery position) to keep airway clear.\n"
             "5. Time the seizure — note start and end time.\n"
             "6. Do NOT restrain the person or put anything in their mouth.",
             "NEVER put your fingers or any object in a seizing person's mouth — you WILL be bitten. "
             "They will NOT swallow their tongue.",
             "Call emergency services if: seizure lasts more than 5 minutes, "
             "another seizure starts immediately, breathing does not return to normal after the seizure, "
             "or the person was injured, in water, or pregnant."),

            ("kidney_stones", "Kidney Stone First Aid",
             "1. Drink plenty of water — 2–3 litres per day to help pass the stone.\n"
             "2. Take paracetamol or ibuprofen for pain relief.\n"
             "3. Apply a warm compress to the back or side for comfort.\n"
             "4. Strain urine through a cloth to catch the stone for analysis.\n"
             "5. Seek medical evaluation for imaging and specialist care.",
             "Avoid pain relief stronger than prescribed. "
             "Fever + back pain = possible kidney infection — seek urgent care.",
             "Seek urgent care if: fever with pain, inability to urinate, severe vomiting, "
             "pain not controlled by medications, or blood in urine."),

            ("measles", "Measles First Aid",
             "1. Isolate the patient — measles is extremely contagious for 4 days before and after rash.\n"
             "2. Rest in a well-lit room is fine — light sensitivity is a myth.\n"
             "3. Give paracetamol for fever.\n"
             "4. Ensure plenty of fluids.\n"
             "5. Give Vitamin A supplements — dramatically reduces measles complications.\n"
             "6. Seek medical care immediately.",
             "Measles is vaccine-preventable. Report cases to local health authorities. "
             "Do NOT give aspirin to children.",
             "Seek emergency care if: breathing difficulty, severe rash with fever, "
             "convulsions, confusion, or vision problems."),
        ]

        for key, title, steps, warning, when_help in FA_DATA:
            if key in D:
                FirstAidProcedure.objects.create(
                    disease=D[key],
                    title=title,
                    steps=steps,
                    warning_notes=warning,
                    when_to_seek_help=when_help,
                )

        # ── EMERGENCY KEYWORDS ────────────────────────────────────────────────
        EMERGENCY_DATA = [
            # CRITICAL
            ("not breathing", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112 immediately. Start CPR if trained. Do not leave the patient alone."),
            ("stopped breathing", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112 immediately. Start CPR if trained."),
            ("unconscious", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112 now. Place in recovery position. Do not give food or water."),
            ("cannot breathe", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112 immediately. Keep patient upright and calm."),
            ("heart attack", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112 immediately. Give 300mg aspirin to chew if not allergic. Keep patient still and calm."),
            ("stroke", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112 immediately. Note time symptoms started — clot-busting treatment must be given within 4.5 hours."),
            ("poisoned", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112. Do NOT induce vomiting unless instructed. Note the substance taken."),
            ("snake bite", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112. Keep patient still, immobilise bitten limb. Go to hospital immediately for antivenin."),
            ("drowning", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112. Start CPR if trained. Do not put unconscious person on their back without clearing airway."),
            ("severe bleeding", "CRITICAL", "🚨 EMERGENCY: Apply firm direct pressure to the wound. Call 999 or 112. Do not remove dressings — add more if soaked."),
            ("collapsed", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112. Check breathing. Start CPR if no pulse and no breathing."),
            ("anaphylaxis", "CRITICAL", "🚨 EMERGENCY: Use epinephrine/EpiPen if available. Call 999 or 112 immediately. Lay flat with legs raised unless breathing is difficult."),
            ("allergic reaction severe", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112 immediately if throat swelling, difficulty breathing, or loss of consciousness."),
            ("degedege", "CRITICAL", "🚨 EMERGENCY (Seizure/Convulsions): Call 999 or 112. Do not restrain. Clear area. Do not put anything in mouth."),
            ("convulsions", "CRITICAL", "🚨 EMERGENCY: Protect from injury. Time the seizure. Call 999 or 112 if it lasts more than 5 minutes."),
            ("eclampsia", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112 immediately — pregnant patient having seizures needs urgent hospital care."),
            ("coughing blood", "CRITICAL", "🚨 EMERGENCY: Call 999 or 112. Sit upright. Could indicate TB, lung injury, or severe pneumonia."),
            # URGENT
            ("chest pain", "URGENT", "⚠️ URGENT: Chest pain may indicate a heart attack. Seek emergency care immediately. Call 999 or 112 if severe."),
            ("difficulty breathing", "URGENT", "⚠️ URGENT: Seek medical care immediately. Sit upright. If asthmatic, use your inhaler. Call 999 or 112 if severe."),
            ("seizure", "URGENT", "⚠️ URGENT: Seek medical care after the seizure stops. Call 999 or 112 if it lasts over 5 minutes."),
            ("high fever", "URGENT", "⚠️ URGENT: Fever above 39°C in adults or 38°C in children under 5 requires prompt medical evaluation. Give paracetamol and go to hospital."),
            ("meningitis", "URGENT", "⚠️ URGENT: Stiff neck + fever + headache = possible meningitis. Seek emergency care immediately."),
            ("baby not breathing", "URGENT", "🚨 EMERGENCY: Call 999 or 112 immediately. Start infant CPR if trained."),
            ("child not waking up", "URGENT", "🚨 EMERGENCY: Call 999 or 112 immediately."),
            ("very dehydrated", "URGENT", "⚠️ URGENT: Start ORS immediately and transport to hospital. IV fluids may be needed."),
            ("blood in stool", "URGENT", "⚠️ URGENT: Blood in stool requires medical evaluation today — could indicate dysentery, typhoid, or bowel problem."),
            ("blood in urine", "URGENT", "⚠️ URGENT: Seek medical care promptly — could be UTI, kidney stones, schistosomiasis, or cancer."),
            # CAUTION
            ("fever", "CAUTION", "⚠️ CAUTION: Give paracetamol, encourage fluids, and rest. Seek medical care if fever is above 39°C or lasts more than 3 days."),
            ("malaria symptoms", "CAUTION", "⚠️ CAUTION: Get tested for malaria at the nearest health facility. Do not self-treat without a confirmed diagnosis."),
            ("diarrhea", "CAUTION", "⚠️ CAUTION: Start ORS immediately. Seek medical care if diarrhea lasts more than 2 days, contains blood, or patient is very young or elderly."),
            ("vomiting", "CAUTION", "⚠️ CAUTION: Rest the stomach, sip ORS or water. Seek care if vomiting is persistent, contains blood, or is accompanied by severe abdominal pain."),
        ]

        for keyword, severity, message in EMERGENCY_DATA:
            EmergencyKeyword.objects.create(
                keyword=keyword,
                severity=severity,
                response_message=message,
            )
