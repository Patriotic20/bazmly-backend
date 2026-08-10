"""seed uzbek regions and districts

Data-only revision, in the same spirit as `b7834c92fef5`: a single
`alembic upgrade head` has to yield a database the app can actually run on, and
`venues.district_id` is NOT NULL, so an empty `regions` / `districts` pair makes
onboarding impossible.

Every first-level unit of Uzbekistan (12 viloyat, Qoraqalpog'iston and Toshkent
shahri) and every second-level unit under them -- 209 rows covering both tuman
and city-of-regional-subordination, which `districts` deliberately holds in one
table. Names and the parent/child structure follow the SOATO register; the city
rows are spelled `<name> shahri` so a picker can tell `Andijon tumani` from
`Andijon shahri`.

`regions.code` is ISO 3166-2:UZ, which is what `RegionCreate` already validates
against, so the seeded rows and anything the admin API writes share one format.

The coordinates are district centres resolved from OpenStreetMap. They are good
enough to centre a map or sort a "nearest first" list -- they are not survey
data, and nothing in the schema treats them as authoritative: a venue carries its
own `latitude` / `longitude` and its own PostGIS `location`.

Revision ID: 944af78cfba8
Revises: 64f95e4f640a
Create Date: 2026-08-10 20:16:38.514139

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "944af78cfba8"
down_revision: str | Sequence[str] | None = "64f95e4f640a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ISO 3166-2:UZ code -> Uzbek name. Toshkent shahri leads because it is where
# the product launches; the rest are alphabetical.
REGIONS = [
    ("UZ-TK", "Toshkent shahri"),
    ("UZ-AN", "Andijon"),
    ("UZ-BU", "Buxoro"),
    ("UZ-JI", "Jizzax"),
    ("UZ-QA", "Qashqadaryo"),
    ("UZ-NW", "Navoiy"),
    ("UZ-NG", "Namangan"),
    ("UZ-SA", "Samarqand"),
    ("UZ-SI", "Sirdaryo"),
    ("UZ-SU", "Surxondaryo"),
    ("UZ-TO", "Toshkent"),
    ("UZ-FA", "Farg'ona"),
    ("UZ-XO", "Xorazm"),
    ("UZ-QR", "Qoraqalpog'iston Respublikasi"),
]

# region code, name, latitude, longitude
DISTRICTS = [
    ("UZ-TK", "Bektemir tumani", "41.228110", "69.320569"),
    ("UZ-TK", "Chilonzor tumani", "41.284726", "69.215219"),
    ("UZ-TK", "Mirobod tumani", "41.282700", "69.293251"),
    ("UZ-TK", "Mirzo Ulug'bek tumani", "41.333142", "69.349888"),
    ("UZ-TK", "Olmazor tumani", "41.362149", "69.226602"),
    ("UZ-TK", "Shayxontohur tumani", "41.325000", "69.230000"),
    ("UZ-TK", "Sirg'ali tumani", "41.246451", "69.236905"),
    ("UZ-TK", "Uchtepa tumani", "41.304365", "69.160313"),
    ("UZ-TK", "Yakkasaroy tumani", "41.284560", "69.252983"),
    ("UZ-TK", "Yangihayot tumani", "41.188860", "69.215240"),
    ("UZ-TK", "Yashnobod tumani", "41.288214", "69.330865"),
    ("UZ-TK", "Yunusobod tumani", "41.351486", "69.298969"),
    ("UZ-AN", "Andijon shahri", "40.783347", "72.350675"),
    ("UZ-AN", "Andijon tumani", "40.800000", "72.416667"),
    ("UZ-AN", "Asaka tumani", "40.666667", "72.250000"),
    ("UZ-AN", "Baliqchi tumani", "40.866667", "72.000000"),
    ("UZ-AN", "Bo'z tumani", "40.689033", "71.925420"),
    ("UZ-AN", "Buloqboshi tumani", "40.617027", "72.496214"),
    ("UZ-AN", "Izboskan tumani", "40.916667", "72.250000"),
    ("UZ-AN", "Jalaquduq tumani", "40.726379", "72.627602"),
    ("UZ-AN", "Marxamat tumani", "40.500959", "72.309663"),
    ("UZ-AN", "Oltinko'l tumani", "40.801147", "72.163416"),
    ("UZ-AN", "Paxtaobod tumani", "40.966654", "72.412191"),
    ("UZ-AN", "Qo'rg'ontepa tumani", "40.733957", "72.762862"),
    ("UZ-AN", "Shahrixon tumani", "40.716667", "72.066667"),
    ("UZ-AN", "Ulug'nor tumani", "40.761845", "71.701069"),
    ("UZ-AN", "Xo'jaobod tumani", "40.666667", "72.583333"),
    ("UZ-AN", "Xonobod shahri", "40.801029", "72.986647"),
    ("UZ-BU", "Buxoro shahri", "39.775984", "64.415153"),
    ("UZ-BU", "Buxoro tumani", "39.574099", "64.323970"),
    ("UZ-BU", "G'ijduvon tumani", "40.483472", "64.771709"),
    ("UZ-BU", "Jondor tumani", "39.765838", "64.148483"),
    ("UZ-BU", "Kogon shahri", "39.724500", "64.545184"),
    ("UZ-BU", "Kogon tumani", "39.767238", "64.570845"),
    ("UZ-BU", "Olot tumani", "39.257111", "64.114482"),
    ("UZ-BU", "Peshku tumani", "40.726124", "63.292524"),
    ("UZ-BU", "Qorako'l tumani", "40.000000", "63.000000"),
    ("UZ-BU", "Qorovulbozor tumani", "39.445936", "64.743133"),
    ("UZ-BU", "Romitan tumani", "40.685547", "62.621013"),
    ("UZ-BU", "Shofirkon tumani", "40.500000", "64.333333"),
    ("UZ-BU", "Vobkent tumani", "40.000000", "64.500000"),
    ("UZ-JI", "Arnasoy tumani", "40.532846", "67.852411"),
    ("UZ-JI", "Baxmal tumani", "39.792470", "67.753214"),
    ("UZ-JI", "Do'stlik tumani", "40.571667", "68.049589"),
    ("UZ-JI", "Forish tumani", "40.459338", "67.222579"),
    ("UZ-JI", "G'allaorol tumani", "40.082532", "67.384395"),
    ("UZ-JI", "Jizzax shahri", "40.133180", "67.823408"),
    ("UZ-JI", "Mirzacho'l tumani", "40.666667", "68.083333"),
    ("UZ-JI", "Paxtakor tumani", "40.356024", "68.047965"),
    ("UZ-JI", "Sh.Rashidov tumani", "40.081193", "67.865149"),
    ("UZ-JI", "Yangiobod tumani", "40.018716", "68.753185"),
    ("UZ-JI", "Zafarobod tumani", "40.357550", "67.795705"),
    ("UZ-JI", "Zarbdor tumani", "40.161861", "68.166251"),
    ("UZ-JI", "Zomin tumani", "40.001508", "68.329467"),
    ("UZ-QA", "Chiroqchi tumani", "39.205014", "66.486577"),
    ("UZ-QA", "Dehqonobod tumani", "38.333333", "66.666667"),
    ("UZ-QA", "G'uzor tumani", "38.500000", "66.000000"),
    ("UZ-QA", "Kasbi tumani", "38.896469", "65.394709"),
    ("UZ-QA", "Kitob tumani", "39.163158", "67.011976"),
    ("UZ-QA", "Ko'kdala tumani", "39.136493", "66.198555"),
    ("UZ-QA", "Koson tumani", "39.166667", "65.750000"),
    ("UZ-QA", "Mirishkor tumani", "38.827449", "64.919801"),
    ("UZ-QA", "Muborak tumani", "39.266667", "65.166667"),
    ("UZ-QA", "Nishon tumani", "38.583333", "65.583333"),
    ("UZ-QA", "Qamashi tumani", "38.715428", "66.731960"),
    ("UZ-QA", "Qarshi shahri", "38.839824", "65.792779"),
    ("UZ-QA", "Qarshi tumani", "38.805358", "65.717078"),
    ("UZ-QA", "Shahrisabz shahri", "39.052582", "66.827864"),
    ("UZ-QA", "Shahrisabz tumani", "39.005328", "67.113508"),
    ("UZ-QA", "Yakkabog' tumani", "38.884872", "66.848142"),
    ("UZ-NW", "G'ozg'on tumani", "40.589421", "65.493999"),
    ("UZ-NW", "Karmana tumani", "40.048118", "65.203857"),
    ("UZ-NW", "Konimex tumani", "41.005243", "64.327364"),
    ("UZ-NW", "Navbahor tumani", "40.200000", "65.333333"),
    ("UZ-NW", "Navoiy shahri", "40.103458", "65.373422"),
    ("UZ-NW", "Nurota tumani", "40.666667", "66.000000"),
    ("UZ-NW", "Qiziltepa tumani", "39.916667", "65.000000"),
    ("UZ-NW", "Tomdi tumani", "41.619553", "64.962153"),
    ("UZ-NW", "Uchquduq tumani", "42.153277", "63.562210"),
    ("UZ-NW", "Xatirchi tumani", "40.193422", "65.907303"),
    ("UZ-NW", "Zarafshon shahri", "41.571927", "64.196130"),
    ("UZ-NG", "Chortoq tumani", "41.166667", "71.833333"),
    ("UZ-NG", "Chust tumani", "40.999506", "71.241596"),
    ("UZ-NG", "Davlatobod tumani", "41.007970", "71.579239"),
    ("UZ-NG", "Kosonsoy tumani", "41.166667", "71.533333"),
    ("UZ-NG", "Mingbuloq tumani", "40.750000", "71.250000"),
    ("UZ-NG", "Namangan shahri", "40.999648", "71.672624"),
    ("UZ-NG", "Namangan tumani", "40.930394", "71.647659"),
    ("UZ-NG", "Norin tumani", "40.916667", "72.000000"),
    ("UZ-NG", "Pop tumani", "41.000000", "70.833333"),
    ("UZ-NG", "To'raqo'rg'on tumani", "40.999107", "71.508865"),
    ("UZ-NG", "Uchqo'rg'on tumani", "41.114560", "72.077628"),
    ("UZ-NG", "Uychi tumani", "41.033333", "71.916667"),
    ("UZ-NG", "Yangi Namangan tumani", "41.073816", "71.625016"),
    ("UZ-NG", "Yangiqo'rg'on tumani", "41.188938", "71.725735"),
    ("UZ-SA", "Bulung'ur tumani", "39.760030", "67.276067"),
    ("UZ-SA", "Ishtixon tumani", "40.000000", "66.500000"),
    ("UZ-SA", "Jomboy tumani", "39.750000", "67.166667"),
    ("UZ-SA", "Kattaqo'rg'on shahri", "39.901812", "66.268494"),
    ("UZ-SA", "Kattaqo'rg'on tumani", "39.950000", "66.300000"),
    ("UZ-SA", "Narpay tumani", "39.917908", "65.989039"),
    ("UZ-SA", "Nurobod tumani", "39.666667", "66.000000"),
    ("UZ-SA", "Oqdaryo tumani", "39.833333", "66.800000"),
    ("UZ-SA", "Pastdarg'om tumani", "39.650000", "66.666667"),
    ("UZ-SA", "Paxtachi tumani", "39.886289", "65.500061"),
    ("UZ-SA", "Payariq tumani", "40.000000", "66.916667"),
    ("UZ-SA", "Qo'shrabot tumani", "40.333333", "66.500000"),
    ("UZ-SA", "Samarqand shahri", "39.655002", "66.975695"),
    ("UZ-SA", "Samarqand tumani", "39.583333", "66.916667"),
    ("UZ-SA", "Tayloq tumani", "39.583333", "67.116667"),
    ("UZ-SA", "Urgut tumani", "39.405986", "67.179381"),
    ("UZ-SI", "Baxt shahri", "40.720440", "68.692619"),
    ("UZ-SI", "Boyovut tumani", "40.366667", "69.000000"),
    ("UZ-SI", "Guliston shahri", "40.495982", "68.775868"),
    ("UZ-SI", "Guliston tumani", "40.500000", "68.916667"),
    ("UZ-SI", "Mirzaobod tumani", "40.472681", "68.624438"),
    ("UZ-SI", "Oqoltin tumani", "40.546975", "68.318227"),
    ("UZ-SI", "Sardoba tumani", "40.326005", "68.303121"),
    ("UZ-SI", "Sayxunobod tumani", "40.679445", "68.787172"),
    ("UZ-SI", "Shirin shahri", "40.230299", "69.126309"),
    ("UZ-SI", "Sirdaryo tumani", "40.802674", "68.643321"),
    ("UZ-SI", "Xovos tumani", "40.244165", "68.865175"),
    ("UZ-SI", "Yangiyer shahri", "40.270075", "68.816598"),
    ("UZ-SU", "Angor tumani", "37.442176", "67.242305"),
    ("UZ-SU", "Bandixon tumani", "37.816461", "67.359424"),
    ("UZ-SU", "Boysun tumani", "38.140407", "67.130993"),
    ("UZ-SU", "Denov tumani", "38.345719", "67.854993"),
    ("UZ-SU", "Jarqo'rg'on tumani", "37.509160", "67.420649"),
    ("UZ-SU", "Muzrabot tumani", "37.415218", "66.854533"),
    ("UZ-SU", "Oltinsoy tumani", "38.223326", "67.706908"),
    ("UZ-SU", "Qiziriq tumani", "37.647256", "67.247577"),
    ("UZ-SU", "Qumqo'rg'on tumani", "37.829321", "67.594958"),
    ("UZ-SU", "Sariosiyo tumani", "38.721146", "67.831391"),
    ("UZ-SU", "Sherobod tumani", "37.687232", "66.916191"),
    ("UZ-SU", "Sho'rchi tumani", "37.966720", "67.874780"),
    ("UZ-SU", "Termiz shahri", "37.244247", "67.283151"),
    ("UZ-SU", "Termiz tumani", "37.332136", "67.516372"),
    ("UZ-SU", "Uzun tumani", "38.228774", "68.150617"),
    ("UZ-TO", "Angren shahri", "41.021221", "70.079536"),
    ("UZ-TO", "Bekobod shahri", "40.232029", "69.253141"),
    ("UZ-TO", "Bekobod tumani", "40.416667", "69.166667"),
    ("UZ-TO", "Bo'ka tumani", "40.750000", "69.166667"),
    ("UZ-TO", "Bo'stonliq tumani", "41.666667", "70.000000"),
    ("UZ-TO", "Chinoz tumani", "41.001730", "68.835698"),
    ("UZ-TO", "Chirchiq shahri", "41.472616", "69.581192"),
    ("UZ-TO", "Nurafshon shahri", "41.027688", "69.346057"),
    ("UZ-TO", "O'rtachirchiq tumani", "41.083655", "69.329137"),
    ("UZ-TO", "Ohangaron shahri", "40.905354", "69.640071"),
    ("UZ-TO", "Ohangaron tumani", "41.000000", "70.000000"),
    ("UZ-TO", "Olmaliq shahri", "40.845729", "69.607161"),
    ("UZ-TO", "Oqqo'rg'on tumani", "40.878535", "69.044367"),
    ("UZ-TO", "Parkent tumani", "41.300000", "69.666667"),
    ("UZ-TO", "Piskent tumani", "40.834608", "69.502715"),
    ("UZ-TO", "Qibray tumani", "41.500000", "69.500000"),
    ("UZ-TO", "Quyichirchiq tumani", "40.916667", "69.000000"),
    ("UZ-TO", "Toshkent tumani", "41.425097", "69.226947"),
    ("UZ-TO", "Yangiyo'l shahri", "41.119599", "69.056813"),
    ("UZ-TO", "Yangiyo'l tumani", "41.104743", "69.010902"),
    ("UZ-TO", "Yuqorichirchiq tumani", "41.256234", "69.526931"),
    ("UZ-TO", "Zangiota tumani", "41.250000", "69.083333"),
    ("UZ-FA", "Beshariq tumani", "40.433333", "70.600000"),
    ("UZ-FA", "Bog'dod tumani", "40.480930", "71.258103"),
    ("UZ-FA", "Buvayda tumani", "40.566774", "71.180572"),
    ("UZ-FA", "Dang'ara tumani", "40.578097", "70.921237"),
    ("UZ-FA", "Farg'ona shahri", "40.376488", "71.791319"),
    ("UZ-FA", "Farg'ona tumani", "40.376488", "71.791319"),
    ("UZ-FA", "Furqat tumani", "40.505436", "70.780850"),
    ("UZ-FA", "Marg'ilon shahri", "40.469487", "71.719491"),
    ("UZ-FA", "O'zbekiston tumani", "40.351133", "70.862994"),
    ("UZ-FA", "Oltiariq tumani", "40.412206", "71.519462"),
    ("UZ-FA", "Qo'qon shahri", "40.533168", "70.940090"),
    ("UZ-FA", "Qo'shtepa tumani", "40.523948", "71.599581"),
    ("UZ-FA", "Quva tumani", "40.513304", "72.060954"),
    ("UZ-FA", "Quvasoy shahri", "40.293915", "71.985103"),
    ("UZ-FA", "Rishton tumani", "40.366667", "71.250000"),
    ("UZ-FA", "So'x tumani", "40.035898", "71.071498"),
    ("UZ-FA", "Toshloq tumani", "40.492037", "71.838912"),
    ("UZ-FA", "Uchko'prik tumani", "40.546725", "71.055158"),
    ("UZ-FA", "Yozyovon tumani", "40.634917", "71.706753"),
    ("UZ-XO", "Bog'ot tumani", "41.350000", "60.833333"),
    ("UZ-XO", "Gurlan tumani", "41.894697", "60.279088"),
    ("UZ-XO", "Qo'shko'pir tumani", "41.533715", "60.351907"),
    ("UZ-XO", "Shovot tumani", "41.666667", "60.250000"),
    ("UZ-XO", "Tuproqqal'a tumani", "41.183165", "61.786343"),
    ("UZ-XO", "Urganch shahri", "41.551790", "60.631281"),
    ("UZ-XO", "Urganch tumani", "41.575339", "60.599912"),
    ("UZ-XO", "Xazorasp tumani", "41.250000", "61.166667"),
    ("UZ-XO", "Xiva shahri", "41.377510", "60.363455"),
    ("UZ-XO", "Xiva tumani", "41.374101", "60.329673"),
    ("UZ-XO", "Xonqa tumani", "41.481964", "60.789682"),
    ("UZ-XO", "Yangiariq tumani", "41.333333", "60.583333"),
    ("UZ-XO", "Yangibozor tumani", "41.733066", "60.455368"),
    ("UZ-QR", "Amudaryo tumani", "42.133333", "60.100000"),
    ("UZ-QR", "Beruniy tumani", "42.359973", "60.966655"),
    ("UZ-QR", "Bo'zatov tumani", "43.042007", "59.344031"),
    ("UZ-QR", "Chimboy tumani", "43.000153", "59.750290"),
    ("UZ-QR", "Ellikqal'a tumani", "42.166667", "61.666667"),
    ("UZ-QR", "Kegeyli tumani", "42.774651", "59.611554"),
    ("UZ-QR", "Mo'ynoq tumani", "43.764328", "59.029747"),
    ("UZ-QR", "Nukus shahri", "42.460023", "59.617660"),
    ("UZ-QR", "Nukus tumani", "42.585261", "59.516927"),
    ("UZ-QR", "Qanliko'l tumani", "42.836146", "59.006465"),
    ("UZ-QR", "Qo'ng'irot tumani", "43.045725", "58.847539"),
    ("UZ-QR", "Qorao'zak tumani", "43.028692", "60.016013"),
    ("UZ-QR", "Shumanay tumani", "42.666667", "58.883333"),
    ("UZ-QR", "Taxiatosh tumani", "42.337314", "59.535127"),
    ("UZ-QR", "Taxtako'pir tumani", "43.020721", "60.289334"),
    ("UZ-QR", "To'rtko'l tumani", "41.561978", "60.992374"),
    ("UZ-QR", "Xo'jayli tumani", "42.417046", "59.418258"),
]


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    bind.execute(
        sa.text("INSERT INTO regions (code, name) VALUES (:code, :name)"),
        [{"code": code, "name": name} for code, name in REGIONS],
    )
    # Joined on `code` rather than a returned id: the region rows were just
    # inserted in this transaction and the code is what identifies them.
    bind.execute(
        sa.text(
            "INSERT INTO districts (region_id, name, latitude, longitude) "
            "SELECT r.id, :name, CAST(:latitude AS numeric), CAST(:longitude AS numeric) "
            "FROM regions r WHERE r.code = :code"
        ),
        [
            {"code": code, "name": name, "latitude": latitude, "longitude": longitude}
            for code, name, latitude, longitude in DISTRICTS
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    codes = [code for code, _ in REGIONS]
    bind.execute(
        sa.text(
            "DELETE FROM districts WHERE region_id IN (SELECT id FROM regions WHERE code IN :codes)"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": codes},
    )
    bind.execute(
        sa.text("DELETE FROM regions WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": codes},
    )
