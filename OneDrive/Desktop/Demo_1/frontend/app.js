// ── SVG icon helper ───────────────────────────────────────────────────────────
function ico(id, cls='icon') { return `<svg class="${cls}"><use href="#${id}"/></svg>`; }

// ── i18n dictionary ──────────────────────────────────────────────────────────
const I18N = {
  mn: {
    nav_home:'Нүүр', nav_enroll:'Бүртгэл', nav_monitor:'Хяналт',
    nav_students:'Оюутнууд',
    nav_teacher:'Багш', nav_teacher_dash:'Самбар', nav_parent:'Эцэг эх', nav_admin:'Удирдлага',
    nav_about:'Бидний тухай',
    nav_sections:'Хэсгүүд',
    nav_sec_home:'Нүүр хуудас', nav_sec_prob:'Яагаад хэрэгтэй вэ?',
    nav_sec_feat:'Боломжууд', nav_sec_about:'Бидний тухай', nav_sec_cta:'Эхлэх',
    hero_stat2:'Ирц бүртгэлийн нарийвчлал', hero_stat3:'Нүүр таних хугацаа',
    btn_logout:'Гарах', btn_login_nav:'Нэвтрэх',
    landing_badge:'Mergen AI — Ухаалаг сургалтын систем',
    landing_h1:'Та хэн болохоо сонгоно уу',
    landing_sub:'Таны үүрэгт тохирсон хяналт, мэдэгдэл болон аналитик',
    lp_h1_line1:'Ухаалаг ангийн', lp_h1_line2:'хяналтын систем',
    lp_hero_sub:'AI-д суурилсан ирц бүртгэл, анхаарлын хяналт болон шалгалтын аюулгүй байдлын платформ — нэг дор',
    btn_signin:'Нэвтрэх', btn_register:'Бүртгүүлэх',
    lp_prob_h:'Яагаад хэрэгтэй вэ?', lp_prob_sub:'Монголын сургуулиуд өнөөдөр тулгарч буй бодит асуудлууд',
    lp_feat_h:'Боломжууд', lp_feat_sub:'Нэг платформ дээр бүгдийг шийддэг',
    cap1_h:'Нүүр таних ирц', cap2_h:'Анхаарлын хяналт', cap3_h:'Шалгалтын аюулгүй байдал',
    cap4_h:'Олон самбар', cap5_h:'Edge AI', cap6_h:'Дүрэмт хувцасны хяналт',
    cap6:'Дүрэмт хувцас өмссөн эсэхийг автоматаар шалгана',
    lp_who_h:'Хэнд зориулагдсан вэ?', lp_who_sub:'Үүрэгтээ тохирсон хуваарьт шууд нэвтэрнэ',
    lp_about_sub:'Монголын боловсролыг технологиор дэмжих зорилгоор байгуулагдсан',
    lp_cta_h:'Өнөөдөр эхлэх цаг болжээ', lp_cta_sub:'Бүртгүүлэн системийг туршаад үзнэ үү',
    role_teacher:'Багш', role_teacher_desc:'Хичээлийн анги хяналт, оюутны ирц, анхаарал шинжилгээ',
    role_parent:'Эцэг эх', role_parent_desc:'Хүүхдийнхээ ирц, анхаарал болон хандлагыг хянах',
    role_admin:'Удирдлага', role_admin_desc:'Сургуулийн бүрэн хяналт, бүртгэл, тайлан шинжилгээ',
    btn_enter:'Нэвтрэх', btn_about:'Бидний тухай', btn_get_started:'Эхлэх',
    login_h2:'Нэвтрэх', login_sub:'Нэвтрэх нэр болон нууц үгээ оруулна уу',
    login_choose_role:'Үүрэгээ сонгоно уу',
    lbl_username:'Нэвтрэх нэр', lbl_password:'Нууц үг',
    ph_username:'нэвтрэх нэр', ph_password:'нууц үг',
    btn_login:'Нэвтрэх', login_no_acc:'Бүртгэл байхгүй юу?', btn_signup_link:'Бүртгүүлэх',
    btn_back:'← Буцах',
    signup_h2:'Бүртгүүлэх', signup_sub:'Шинэ бүртгэл үүсгэх', signup_choose_role:'Үүрэгээ сонгоно уу',
    lbl_fullname:'Бүтэн нэр', ph_fullname:'Таны бүтэн нэр',
    lbl_child:'Хүүхэд сонгох', ph_child:'— оюутан сонгоно уу —',
    btn_signup:'Бүртгүүлэх', signup_has_acc:'Бүртгэл байна уу?', btn_login_link:'Нэвтрэх',
    about_sub:'Ухаалаг ангийн хяналтын систем',
    about_mission_h:'Бидний эрхэм зорилго',
    about_mission_p:'Mergen AI нь сургуулийн анги танхимын хяналтыг хиймэл оюун ухааны технологиор дэмжиж, багш болон эцэг эхчүүдэд оюутнуудын ирц, анхаарал болон хандлагын талаарх бодит цагийн мэдээллийг хүргэдэг.',
    about_features_h:'Үндсэн боломжууд',
    about_f1:'Нүүр таних технологиор оюутны ирцийг автоматаар бүртгэх',
    about_f2:'Анхаарлын түвшинг бодит цагт хянах',
    about_f3:'Шалгалтын горимд утас, зохисгүй хандлагыг илрүүлэх',
    about_f4:'Дүрэмт хувцасны мөрдөлтийг шалгах',
    about_f5:'Эцэг эхэд хүүхдийнхээ мэдээллийг шуурхай хүргэх',
    about_team_h:'Баг',
    about_team_p:'Mergen AI-г Монголын залуу инженер, боловсролын мэргэжилтнүүдийн баг хөгжүүлж байна.',
    role_lbl_teacher:'Багш', role_lbl_parent:'Эцэг эх', role_lbl_admin:'Удирдлага',
    students_h1:'Оюутны бүртгэл',
    students_sub:'Бүртгэлтэй оюутнуудын жагсаалт, нүүрний мэдээлэл, удирдлага',
    stu_face_col:'Нүүрний бүртгэл', stu_registered:'Бүртгэгдсэн', stu_actions:'Үйлдэл',
    stu_search_ph:'Нэрээр хайх…',
    filter_all:'Бүгд', filter_has_face:'Нүүр бүртгэлтэй', filter_no_face:'Нүүр бүртгэлгүй',
    del_confirm_title:'Оюутан устгах уу?', del_confirm_sub:'Энэ үйлдлийг буцаах боломжгүй',
    del_warn:'Оюутны бүх ирц, анхаарлын бүртгэл, мэдэгдэл устгагдана.',
    btn_cancel:'Болих', btn_delete:'Устгах',
    face_yes:'Бүртгэлтэй', face_no:'Бүртгэлгүй',
    stu_total:'Нийт оюутан', stu_with_face:'Нүүр бүртгэлтэй', stu_present:'Өнөөдөр ирсэн',
    btn_reset:'Дахилт', exam_mode:'Шалгалтын горим',
    home_h1:'Mergen AI',
    home_sub:'AI-д суурилсан ирц бүртгэл, анхаарлын хяналт, шалгалтын аюулгүй байдлын платформ',
    feat_face:'Нүүр таних', feat_att:'Анхаарлын хяналт', feat_exam:'Шалгалтын аюулгүй байдал',
    feat_rt:'Бодит цагийн шинжилгээ', feat_alert:'Шуурхай мэдэгдэл', feat_phone:'Утасны илрүүлэлт',
    rc_teacher_h:'Багшийн самбар',
    rc_teacher_p:'Бүх оюутны анхаарлын оноо, шалгалтын мэдэгдэл, бүртгэлийг бодит цагаар харна.',
    rc_parent_h:'Эцэг эхийн самбар',
    rc_parent_p:'Хүүхдийнхээ ирц, анхаарлын дүн, өдрийн гүйцэтгэлийг харна.',
    rc_admin_h:'Удирдлагын самбар',
    rc_admin_p:'Сургуулийн нийт статистик: ирцийн хувь, анхаарал, мэдэгдлийн тойм.',
    rc_open:'Самбар нээх', rc_parent_btn:'Хүүхдээ харах', rc_admin_btn:'Тойм харах',
    getting_started:'Эхлэхийн тулд',
    btn_new_student:'Шинэ оюутан бүртгэх', btn_live_mon:'Бодит цагийн хяналт',
    about_h:'Бидний тухай', about_sub:'Mergen AI гэж юу вэ? Яагаад Монголын сургуулиудад зайлшгүй шаардлагатай вэ?',
    about_p1:'Mergen AI нь камерын дүрс боловсруулалт болон хиймэл оюун ухааныг ашиглан ангийн үйл ажиллагааг бодит цагаар ажиглаж, багш болон эцэг эхэд мэдээлэл өгдөг систем юм.',
    about_p2:'Монголын хувийн сургуулиуд руу нэвтрэхийг зорьж байгаа бөгөөд Улаанбаатарт 600 гаруй хувийн сургууль үйл ажиллагаа явуулж буй, жил бүр 12%-иар өсч буй энэхүү зах зээлд AI EdTech-ийн орон зай бараг хоосон байна.',
    prob1_h:'Цагийн алдагдал', prob1_p:'Гар ирц бүртгэл 10–15 мин/цаг зарцуулдаг → жилдээ 200+ цаг алддаг',
    prob2_h:'Шалгалтын хуурамч байдал', prob2_p:'Азийн дунд сургуулийн 60%+ оюутан шалгалтын залилан хийсэн гэж хүлээн зөвшөөрдөг',
    prob3_h:'Анхаарлын хяналтгүй байдал', prob3_p:'Багш нар 30+ оюутны анхааралыг нэгэн зэрэг хэмждэг объектив хэрэгсэлгүй',
    market_title:'Зах зээлийн боломж',
    mstat1:'Монгол дахь хувийн сургууль', mstat2:'Жилийн өсөлт', mstat3:'Дэлхийн EdTech AI зах (2030)', mstat4:'CAGR өсөлтийн хурд',
    enroll_h1:'Оюутан бүртгэх',
    enroll_sub:'3 зураг авч нүүрийг бүртгэнэ. Гэрэлтэй газарт бүртгэх нь илүү тохиромжтой.',
    cam_preview:'Камерын урьдчилан харах', cam_hint:'Доор "Камер нээх" дарна уу',
    btn_start_cam:'Камер нээх', btn_capture:'Зураг авах', btn_enroll:'Бүртгэх',
    capture_hint:'3 өнцгөөс зураг авна уу',
    student_info:'Оюутны мэдээлэл', label_name:'Бүтэн нэр', label_class:'Анги', label_role:'Үүрэг',
    role_student:'Оюутан', role_teacher_opt:'Багш',
    ph_name:'Жнь: Тэнүүн Гантулга', ph_class:'Жнь: 10А',
    monitor_h1:'Камерын хяналт',
    monitor_sub:'Нүүр илрүүлэлт · Анхаарлын хяналт · Шалгалтын аюулгүй байдал',
    btn_clear_log:'Лог арилгах',
    cap1:'Нүүр таних технологиор ирцийг автоматаар бүртгэнэ',
    cap2:'Оюутны анхааралыг хэмжиж, бодит цагийн оноо гаргана',
    cap3:'Шалгалтын горимд утас хэрэглэлт болон сэжигтэй хөдөлгөөнийг илрүүлнэ',
    cap4:'Багш, эцэг эх, удирдлагад тус тусдаа самбар, мэдэгдэл',
    cap5:'Интернэтгүйгээр ажиллах боломжтой (Edge AI)',
    cam_off:'Унтарсан', cam_on:'Ажиллаж байна',
    btn_start_mon:'Камер эхлүүлэх', btn_stop:'Зогсоох',
    monitor_tip:'Зөвлөгөө: Бүртгэлийн камераа нээсэн бол эхлэх үед хаана уу. Шалгалтын горимд доош харвал утас хэрэглэсэн гэж тооцно.',
    detected_faces:'Илрүүлсэн нүүрнүүд', no_faces:'Нүүр илрүүлэгдээгүй',
    recent_alerts:'Сүүлийн мэдэгдэл', no_alerts:'Мэдэгдэл байхгүй',
    teacher_h1:'Багшийн самбар',
    stat_present:'Ирсэн', stat_absent:'Ирээгүй', stat_avg_att:'Дундаж анхаарал', stat_alerts:'Мэдэгдэл',
    today_att:'Өнөөдрийн ирц',
    col_name:'Нэр', col_arrived:'Ирсэн цаг', col_att:'Анхаарал', col_alerts:'Мэдэгдэл',
    col_status:'Төлөв', col_class:'Анги',
    chart_title:'Ангийн анхаарал цагаар',
    notif_log:'Мэдэгдлийн бүртгэл', notif_log_hint:'P товч — утасны дуурайлга',
    btn_notif:'Мэдэгдэл',
    parent_h1:'Эцэг эхийн самбар', parent_sub:'Хүүхдийнхээ ирц, анхаарлын тойм',
    student_lbl:'Оюутан', att_score:'Анхаарлын оноо', today_summary:'Өнөөдрийн тойм',
    loading:'Уншиж байна…',
    p_arrived:'Ирсэн цаг:', p_alerts:'Өнөөдрийн мэдэгдэл:', p_present:'Өнөөдөр ирсэн',
    p_absent:'Өнөөдөр ирээгүй',
    yesterday_att:'Өчигдрийн ирц', att_history:'Ирцийн түүх',
    hist_present:'Ирсэн', hist_absent:'Ирээгүй', hist_no_data:'Мэдээлэл байхгүй',
    admin_h1:'Удирдлагын самбар',
    admin_sub:'Сургуулийн нийт шинжилгээ ба гүйцэтгэлийн тойм',
    stat_enrolled:'Бүртгэлтэй', stat_rate:'Ирцийн хувь',
    class_breakdown:'Ангийн дэлгэрэнгүй', alert_summary:'Мэдэгдлийн тойм',
    badge_present:'Ирсэн', badge_absent:'Ирээгүй',
    alert_suspicious:'Сэжигтэй хөдөлгөөн', alert_phone:'Утас хэрэглэсэн',
    alert_down:'Доош харж байна', alert_unknown:'Зорчигч илрүүлэгдсэн',
    uniform_h:'Дүрэмт хувцас', uniform_rate:'Дүрэмт хувцасны хувь',
    uniform_wearing:'Хувцастай', uniform_not:'Хувцасгүй', uniform_weekly:'7 хоногийн дундаж',
    uniform_checked:'Шалгагдсан', col_uniform:'Дүрэмт хувцас', uniform_yes:'✓ Хувцастай',
    uniform_no:'✗ Хувцасгүй', uniform_unk:'Шалгаагүй',
    status_att:'Анхааралтай', status_dist:'Анхаарал сарнисан', status_susp:'Сэжигтэй',
    status_down:'Доош харж байна',
    enroll_ok:'бүртгэгдлээ! зураг боловсруулагдлаа.',
    enroll_fail:'Нүүр илрүүлэгдсэнгүй. Гэрэлтэй газарт дахин оролдоно уу.',
    no_student:'Бүртгэлтэй оюутан байхгүй',
    err_fill:'Бүх талбарыг бөглөнө үү',
    label_role:'Үүрэг',
  },
  en: {
    nav_home:'Home', nav_enroll:'Enroll', nav_monitor:'Monitor',
    nav_students:'Students',
    nav_teacher:'Teacher', nav_teacher_dash:'Dashboard', nav_parent:'Parent', nav_admin:'Admin',
    nav_about:'About',
    nav_sections:'Sections',
    nav_sec_home:'Home', nav_sec_prob:'Why it matters',
    nav_sec_feat:'Features', nav_sec_about:'About us', nav_sec_cta:'Get started',
    hero_stat2:'Attendance accuracy', hero_stat3:'Face recognition speed',
    btn_logout:'Sign out', btn_login_nav:'Sign in',
    landing_badge:'Mergen AI — Smart Classroom System',
    landing_h1:'Choose your role',
    landing_sub:'Monitoring, alerts, and analytics tailored for you',
    lp_h1_line1:'Smart Classroom', lp_h1_line2:'Monitoring System',
    lp_hero_sub:'AI-powered attendance, attention monitoring & exam security platform — all in one',
    btn_signin:'Sign in', btn_register:'Sign up',
    lp_prob_h:'Why is it needed?', lp_prob_sub:'Real challenges faced by schools today',
    lp_feat_h:'Features', lp_feat_sub:'Everything you need in one platform',
    cap1_h:'Face ID Attendance', cap2_h:'Attention Monitoring', cap3_h:'Exam Security',
    cap4_h:'Multi-role Dashboards', cap5_h:'Edge AI', cap6_h:'Uniform Compliance',
    cap6:'Automatically checks whether students are wearing their uniform',
    lp_who_h:'Who is it for?', lp_who_sub:'Sign in directly to your role-specific dashboard',
    lp_about_sub:'Built to support Mongolian education through technology',
    lp_cta_h:"It's time to get started", lp_cta_sub:'Sign up and try the system today',
    role_teacher:'Teacher', role_teacher_desc:'Class monitoring, attendance, and attention analytics',
    role_parent:'Parent', role_parent_desc:"Track your child's attendance, attention, and behavior",
    role_admin:'Admin', role_admin_desc:'Full school oversight, registrations, and reports',
    btn_enter:'Sign in', btn_about:'About us', btn_get_started:'Get started',
    login_h2:'Sign in', login_sub:'Enter your username and password',
    login_choose_role:'Select your role',
    lbl_username:'Username', lbl_password:'Password',
    ph_username:'username', ph_password:'password',
    btn_login:'Sign in', login_no_acc:"Don't have an account?", btn_signup_link:'Sign up',
    btn_back:'← Back',
    signup_h2:'Sign up', signup_sub:'Create a new account', signup_choose_role:'Select your role',
    lbl_fullname:'Full name', ph_fullname:'Your full name',
    lbl_child:'Select child', ph_child:'— select student —',
    btn_signup:'Sign up', signup_has_acc:'Already have an account?', btn_login_link:'Sign in',
    about_sub:'Smart classroom monitoring system',
    about_mission_h:'Our mission',
    about_mission_p:'Mergen AI uses AI and camera vision to monitor classrooms in real time, providing teachers and parents with live data on attendance, attention, and student behavior.',
    about_features_h:'Features',
    about_f1:'Automated attendance via face recognition',
    about_f2:'Real-time attention level tracking',
    about_f3:'Phone and suspicious behavior detection in exam mode',
    about_f4:'Uniform compliance checking',
    about_f5:"Instant alerts to parents about their child's status",
    about_team_h:'Team',
    about_team_p:'Mergen AI is built by a team of Mongolian engineers and education specialists.',
    role_lbl_teacher:'Teacher', role_lbl_parent:'Parent', role_lbl_admin:'Admin',
    students_h1:'Student Management',
    students_sub:'All enrolled students, face registration status, and management',
    stu_face_col:'Face ID', stu_registered:'Registered', stu_actions:'Actions',
    stu_search_ph:'Search by name…',
    filter_all:'All', filter_has_face:'Has face', filter_no_face:'No face',
    del_confirm_title:'Delete student?', del_confirm_sub:'This action cannot be undone',
    del_warn:'All attendance, attention logs and alerts for this student will be deleted.',
    btn_cancel:'Cancel', btn_delete:'Delete',
    face_yes:'Registered', face_no:'Not registered',
    stu_total:'Total students', stu_with_face:'With face ID', stu_present:'Present today',
    btn_reset:'Reset', exam_mode:'Exam Mode',
    home_h1:'Mergen AI',
    home_sub:'AI-powered attendance tracking, attention monitoring & exam integrity platform',
    feat_face:'Face Recognition', feat_att:'Attention Tracking', feat_exam:'Exam Integrity',
    feat_rt:'Real-time Analytics', feat_alert:'Instant Alerts', feat_phone:'Phone Detection',
    rc_teacher_h:'Teacher Dashboard',
    rc_teacher_p:'View all students, attention scores, exam alerts and logs in real time.',
    rc_parent_h:'Parent Dashboard',
    rc_parent_p:"Check your child's attendance, attention score and daily performance.",
    rc_admin_h:'Admin Dashboard',
    rc_admin_p:'School-wide stats: attendance rate, class engagement, alert summary.',
    rc_open:'Open dashboard', rc_parent_btn:'View your child', rc_admin_btn:'School overview',
    getting_started:'Getting started',
    btn_new_student:'Enroll New Student', btn_live_mon:'Live Monitor',
    about_h:'About Us', about_sub:'What is Mergen AI? Why does Mongolia need it?',
    about_p1:'Mergen AI uses computer vision and AI to monitor classroom activity in real time, giving teachers and parents instant insight into attendance, attention, and exam behaviour.',
    about_p2:'Launching in private schools across Ulaanbaatar — a market of 600+ private schools growing 12% annually where AI EdTech penetration is virtually zero.',
    prob1_h:'Wasted class time', prob1_p:'Manual roll call consumes 10–15 min per period → 200+ hours of instruction lost per school per year',
    prob2_h:'Exam cheating', prob2_p:'60%+ of students in Asian secondary schools admit to some form of cheating in exams',
    prob3_h:'No attention data', prob3_p:'Teachers have no objective tool to measure engagement across 30+ students simultaneously',
    market_title:'Market Opportunity',
    mstat1:'Private schools in Mongolia', mstat2:'Annual enrolment growth', mstat3:'Global EdTech AI market by 2030', mstat4:'CAGR growth rate',
    enroll_h1:'Enroll Student',
    enroll_sub:'Capture 3 photos to register a face embedding. Good lighting = better recognition.',
    cam_preview:'Camera preview', cam_hint:'Click "Start Camera" below',
    btn_start_cam:'Start Camera', btn_capture:'Capture Photo', btn_enroll:'Enroll',
    capture_hint:'Capture from 3 slightly different angles',
    student_info:'Student Information', label_name:'Full Name', label_class:'Class', label_role:'Role',
    role_student:'Student', role_teacher_opt:'Teacher',
    ph_name:'e.g. Tenuun Gantulga', ph_class:'e.g. 10A',
    monitor_h1:'Camera Monitor',
    monitor_sub:'Face detection · Attention tracking · Exam integrity',
    btn_clear_log:'Clear log',
    cap1:'Automatically records attendance using face recognition',
    cap2:'Measures student attention and generates real-time scores',
    cap3:'Detects phone use and suspicious movement in exam mode',
    cap4:'Separate dashboards and alerts for teachers, parents and admins',
    cap5:'Works offline without internet connection (Edge AI)',
    cam_off:'Off', cam_on:'Running',
    btn_start_mon:'Start Camera', btn_stop:'Stop',
    monitor_tip:'Tip: Close the Enroll camera before starting monitor. In exam mode, looking down is flagged as potential phone use.',
    detected_faces:'Detected Faces', no_faces:'No faces detected',
    recent_alerts:'Recent Alerts', no_alerts:'No alerts yet',
    teacher_h1:'Teacher Dashboard',
    stat_present:'Present', stat_absent:'Absent', stat_avg_att:'Avg Attention', stat_alerts:'Alerts',
    today_att:"Today's Attendance",
    col_name:'Name', col_arrived:'Arrived', col_att:'Attention', col_alerts:'Alerts',
    col_status:'Status', col_class:'Class',
    chart_title:'Class Attention Over Time',
    notif_log:'Notification Log', notif_log_hint:'P key — simulate phone detection',
    btn_notif:'Notifications',
    parent_h1:'Parent Dashboard', parent_sub:"Your child's attendance and engagement summary",
    student_lbl:'Student', att_score:'Attention Score', today_summary:"Today's Summary",
    loading:'Loading…',
    p_arrived:'Arrived:', p_alerts:"Today's alerts:", p_present:'Present today',
    p_absent:'Absent today',
    yesterday_att:"Yesterday's Attendance", att_history:'Attendance History',
    hist_present:'Present', hist_absent:'Absent', hist_no_data:'No data',
    admin_h1:'Admin Dashboard',
    admin_sub:'School-wide analytics and performance overview',
    stat_enrolled:'Enrolled', stat_rate:'Attendance Rate',
    class_breakdown:'Class Breakdown', alert_summary:'Alert Summary',
    badge_present:'Present', badge_absent:'Absent',
    alert_suspicious:'Suspicious movement', alert_phone:'Phone detected',
    alert_down:'Looking down', alert_unknown:'Unknown person detected',
    uniform_h:'Uniform', uniform_rate:'Uniform Rate',
    uniform_wearing:'Wearing', uniform_not:'Not Wearing', uniform_weekly:'7-day Avg',
    uniform_checked:'Checked', col_uniform:'Uniform', uniform_yes:'✓ Wearing',
    uniform_no:'✗ Not Wearing', uniform_unk:'Not Checked',
    status_att:'Attentive', status_dist:'Distracted', status_susp:'Suspicious',
    status_down:'Looking down',
    enroll_ok:'enrolled successfully! photos processed.',
    enroll_fail:'No face detected. Try in better lighting.',
    no_student:'No students enrolled',
    err_fill:'Please fill in all fields',
    label_role:'Role',
  }
};

// ── State ────────────────────────────────────────────────────────────────────
const S = {
  lang:          localStorage.getItem('mergen_lang') || 'mn',
  enrollStream:  null,
  captured:      [null, null, null],
  lastAlertId:   0,
  chart:         null,
  pollTimer:     null,
  monTimer:      null,
  cachedAtt:     null,
  cachedUniform: null,
  user:          null,
  token:         localStorage.getItem('mergen_token') || null,
  pendingRole:   null,
};

// ── Translation helpers ──────────────────────────────────────────────────────
function t(key) { return I18N[S.lang][key] || I18N['en'][key] || key; }

function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const k = el.getAttribute('data-i18n');
    const v = I18N[S.lang][k];
    if (v !== undefined) el.textContent = v;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const v = I18N[S.lang][el.getAttribute('data-i18n-placeholder')];
    if (v) el.placeholder = v;
  });
  document.querySelectorAll('[data-i18n-opt]').forEach(el => {
    const v = I18N[S.lang][el.getAttribute('data-i18n-opt')];
    if (v) el.textContent = v;
  });
  document.getElementById('btnMN').classList.toggle('active', S.lang === 'mn');
  document.getElementById('btnEN').classList.toggle('active', S.lang === 'en');
}

function setLang(lang) {
  S.lang = lang;
  localStorage.setItem('mergen_lang', lang);
  applyI18n();
  if (S.cachedAtt) renderAttTable(S.cachedAtt);
  if (S.cachedUniform) renderUniformTable(S.cachedUniform);
  showPage(window.location.pathname);
}

function alertLabel(type) {
  const m = {
    suspicious_glance: t('alert_suspicious'),
    phone_detected:    t('alert_phone'),
    unknown_person:    t('alert_unknown'),
  };
  return m[type] || type;
}

// ── Nav brand ─────────────────────────────────────────────────────────────────
function goHome() {
  if (!S.user) { go({ preventDefault: () => {} }, '/landing'); return; }
  const r = S.user.role;
  if (r === 'admin') go({ preventDefault: () => {} }, '/monitor');
  else if (r === 'parent') go({ preventDefault: () => {} }, '/dashboard/parent');
  else go({ preventDefault: () => {} }, '/dashboard/teacher');
}

// ── Sections scroll ───────────────────────────────────────────────────────────
function toggleNavDD(e) {
  e.stopPropagation();
  const dd = document.getElementById('navSectionsDD');
  dd.classList.toggle('open');
}
document.addEventListener('click', () => {
  document.getElementById('navSectionsDD')?.classList.remove('open');
});

function scrollToSection(id, e) {
  if (e) e.preventDefault();
  document.getElementById('navSectionsDD')?.classList.remove('open');
  const isOnLanding = document.getElementById('page-landing')?.classList.contains('active');
  if (!isOnLanding) {
    go({ preventDefault: () => {} }, '/landing');
    setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150);
    return;
  }
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Auth ──────────────────────────────────────────────────────────────────────
function authHeader() {
  return S.token ? { 'Authorization': `Bearer ${S.token}` } : {};
}

async function apiAuth(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) { const e = await r.json().catch(() => {}); throw new Error(e?.detail || r.statusText); }
  return r.json();
}

function updateNav() {
  const u = S.user;
  const loggedIn = !!u;
  const role = u?.role;
  const isTeacher = role === 'teacher';
  const isAdmin   = role === 'admin';
  const isParent  = role === 'parent';

  document.getElementById('navLoginBtn').style.display = loggedIn ? 'none' : '';
  const regBtn = document.getElementById('navRegisterBtn');
  if (regBtn) regBtn.style.display = loggedIn ? 'none' : '';
  const landingLinks = document.getElementById('navLandingLinks');
  if (landingLinks) landingLinks.style.display = loggedIn ? 'none' : '';

  document.getElementById('navUser').style.display = loggedIn ? 'flex' : 'none';

  document.getElementById('navGroupTeacherFull').style.display = isTeacher ? 'flex' : 'none';
  document.getElementById('navGroupParent').style.display      = isParent  ? 'flex' : 'none';
  document.getElementById('navGroupMain').style.display        = isAdmin   ? 'flex' : 'none';
  document.getElementById('navResetBtn').style.display         = isAdmin   ? '' : 'none';

  if (u) {
    const displayName = u.full_name || u.username;
    document.getElementById('navUserName').textContent = displayName;
    const roleLabels = { teacher: t('role_lbl_teacher'), parent: t('role_lbl_parent'), admin: t('role_lbl_admin') };
    const roleEl = document.getElementById('navUserRole');
    if (roleEl) roleEl.textContent = roleLabels[role] || role;
    const av = document.getElementById('navUserAvatar');
    if (av) av.textContent = displayName.slice(0, 2).toUpperCase();
  }
}

async function loadUser() {
  if (!S.token) return;
  try {
    const r = await fetch('/api/auth/me', { headers: authHeader() });
    if (r.ok) {
      S.user = await r.json();
    } else {
      S.token = null; S.user = null;
      localStorage.removeItem('mergen_token');
    }
  } catch (_) {
    S.token = null; S.user = null;
    localStorage.removeItem('mergen_token');
  }
  updateNav();
}

function logout() {
  S.token = null; S.user = null;
  localStorage.removeItem('mergen_token');
  updateNav();
  go({ preventDefault: () => {} }, '/landing');
}

function goLogin(role) {
  go({ preventDefault: () => {} }, '/login');
}

function goAbout(e) {
  if (typeof e.preventDefault === 'function') e.preventDefault();
  const active = document.querySelector('.page.active');
  if (active && active.id === 'page-landing') {
    document.getElementById('lp-about-section')?.scrollIntoView({ behavior: 'smooth' });
  } else {
    go({ preventDefault: () => {} }, '/about');
  }
}

function selectLoginRole(role) {
  S.pendingRole = role;
  const labels = { teacher: t('role_lbl_teacher'), parent: t('role_lbl_parent'), admin: t('role_lbl_admin') };
  document.getElementById('loginRoleLabel').textContent = labels[role] || role;
  const lsLink = document.getElementById('loginSignupLink');
  if (lsLink) lsLink.style.display = 'none';
  document.getElementById('loginError').style.display = 'none';
  document.getElementById('loginUsername').value = '';
  document.getElementById('loginPassword').value = '';
  document.getElementById('loginStep1').style.display = 'none';
  document.getElementById('loginStep2').style.display = '';
}

function backLoginStep1() {
  document.getElementById('loginStep1').style.display = '';
  document.getElementById('loginStep2').style.display = 'none';
  document.getElementById('loginError').style.display = 'none';
}

function selectSignupRole(role) {
  S.pendingRole = role;
  const labels = { teacher: t('role_lbl_teacher'), parent: t('role_lbl_parent'), admin: t('role_lbl_admin') };
  document.getElementById('signupRoleLabel').textContent = labels[role] || role;
  document.getElementById('signupChildGroup').style.display = role === 'parent' ? '' : 'none';
  document.getElementById('signupError').style.display = 'none';
  document.getElementById('signupStep1').style.display = 'none';
  document.getElementById('signupStep2').style.display = '';
  if (role === 'parent') initSignup();
}

function backSignupStep1() {
  document.getElementById('signupStep1').style.display = '';
  document.getElementById('signupStep2').style.display = 'none';
  document.getElementById('signupError').style.display = 'none';
}

async function doLogin() {
  const btn = document.getElementById('loginBtn');
  const errEl = document.getElementById('loginError');
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value;
  errEl.style.display = 'none';
  if (!username || !password) { errEl.textContent = t('err_fill'); errEl.style.display = ''; return; }
  btn.disabled = true;
  try {
    const res = await api('POST', '/api/auth/login', { username, password });
    S.token = res.token; S.user = res.user;
    localStorage.setItem('mergen_token', res.token);
    updateNav();
    document.getElementById('loginUsername').value = '';
    document.getElementById('loginPassword').value = '';
    const role = res.user.role;
    if (role === 'admin') go({ preventDefault: () => {} }, '/monitor');
    else if (role === 'parent') go({ preventDefault: () => {} }, '/dashboard/parent');
    else go({ preventDefault: () => {} }, '/dashboard/teacher');
  } catch (err) {
    errEl.textContent = err.message;
    errEl.style.display = '';
  } finally { btn.disabled = false; }
}

async function initSignup() {
  const sel = document.getElementById('signupChild');
  sel.innerHTML = `<option value="">${t('ph_child')}</option>`;
  try {
    const students = await api('GET', '/api/auth/students');
    students.forEach(s => {
      const o = document.createElement('option');
      o.value = s.id;
      o.textContent = `${s.name} (${s.class_name})`;
      sel.appendChild(o);
    });
  } catch (_) {}
}

async function doSignup() {
  const btn = document.getElementById('signupBtn');
  const errEl = document.getElementById('signupError');
  const username   = document.getElementById('signupUsername').value.trim();
  const password   = document.getElementById('signupPassword').value;
  const full_name  = document.getElementById('signupFullname').value.trim();
  const student_id = parseInt(document.getElementById('signupChild').value) || null;
  const role       = S.pendingRole || 'parent';
  errEl.style.display = 'none';
  if (!username || !password) { errEl.textContent = t('err_fill'); errEl.style.display = ''; return; }
  btn.disabled = true;
  try {
    const res = await api('POST', '/api/auth/signup', { username, password, role, full_name, student_id });
    S.token = res.token; S.user = res.user;
    localStorage.setItem('mergen_token', res.token);
    updateNav();
    if (role === 'admin') go({ preventDefault: () => {} }, '/monitor');
    else if (role === 'parent') go({ preventDefault: () => {} }, '/dashboard/parent');
    else go({ preventDefault: () => {} }, '/dashboard/teacher');
  } catch (err) {
    errEl.textContent = err.message;
    errEl.style.display = '';
  } finally { btn.disabled = false; }
}

// ── Routing ──────────────────────────────────────────────────────────────────
function go(e, path) {
  if (typeof e.preventDefault === 'function') e.preventDefault();
  if (window.location.pathname === path) return;
  clearInterval(S.pollTimer); clearInterval(S.monTimer);
  if (window.location.pathname === '/monitor') _setVideoSrc(false);
  history.pushState({}, '', path);
  showPage(path);
}
window.addEventListener('popstate', () => showPage(window.location.pathname));

function showPage(path) {
  document.querySelectorAll('.page').forEach(p => {
    p.classList.remove('active');
    p.style.animation = 'none';
    void p.offsetWidth;
    p.style.animation = '';
  });
  document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));

  const MAP = {
    '/':                   ['page-landing',  null],
    '/landing':            ['page-landing',  null],
    '/login':              ['page-login',    null],
    '/signup':             ['page-signup',   null],
    '/about':              ['page-about',    '/about'],
    '/enroll':             ['page-enroll',   '/enroll'],
    '/monitor':            ['page-monitor',       '/monitor'],
    '/students':           ['page-students',      '/students'],
    '/dashboard/teacher':  ['page-teacher',        '/dashboard/teacher'],
    '/dashboard/parent':   ['page-parent',         '/dashboard/parent'],
  };

  const protectedPaths = ['/enroll','/monitor','/students','/dashboard/teacher','/dashboard/parent'];
  if (!S.user && protectedPaths.includes(path)) {
    history.replaceState({}, '', '/landing');
    document.getElementById('page-landing')?.classList.add('active');
    applyI18n();
    return;
  }
  if (path === '/monitor' && S.user && S.user.role !== 'admin') {
    const fallback = S.user.role === 'parent' ? '/dashboard/parent' : '/students';
    history.replaceState({}, '', fallback);
    showPage(fallback);
    return;
  }
  if (['/students','/enroll','/monitor','/dashboard/teacher'].includes(path) && S.user?.role === 'parent') {
    history.replaceState({}, '', '/dashboard/parent');
    showPage('/dashboard/parent');
    return;
  }

  const [pageId, href] = MAP[path] || ['page-landing', null];
  document.getElementById(pageId)?.classList.add('active');
  if (href) {
    document.querySelectorAll(`nav a[href="${href}"]`).forEach(a => a.classList.add('active'));
  }

  const examWrap = document.getElementById('navExamWrap');
  examWrap.style.display = path === '/monitor' ? 'flex' : 'none';

  applyI18n();

  if (path === '/login') {
    document.getElementById('loginStep1').style.display = '';
    document.getElementById('loginStep2').style.display = 'none';
    document.getElementById('loginError').style.display = 'none';
    S.pendingRole = null;
  }
  if (path === '/signup') {
    document.getElementById('signupStep1').style.display = '';
    document.getElementById('signupStep2').style.display = 'none';
    document.getElementById('signupError').style.display = 'none';
    S.pendingRole = null;
  }
  if (path === '/students')       initStudents();
  if (path === '/monitor')           initMonitor();
  if (path === '/dashboard/teacher') initTeacher();
  if (path === '/dashboard/parent')  initParent();
}

// ── API helper ───────────────────────────────────────────────────────────────
async function api(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: {'Content-Type':'application/json', ...authHeader()},
    body: body ? JSON.stringify(body) : undefined
  });
  if (!r.ok) { const e = await r.json().catch(()=>{}); throw new Error(e?.detail || r.statusText); }
  return r.json();
}

// ── Toast ────────────────────────────────────────────────────────────────────
function toast(msg, type='info') {
  const el = document.getElementById('toast');
  const colors = { info:'#15803D', success:'#059669', error:'#DC2626', warning:'#D97706' };
  el.style.borderLeft = `3px solid ${colors[type]||colors.info}`;
  el.innerHTML = `<svg class="icon" style="color:${colors[type]||colors.info}"><use href="#i-bell"/></svg> ${msg}`;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3200);
}

function fmtTime(ts) {
  if (!ts) return '—';
  return new Date(ts).toLocaleTimeString(S.lang==='mn'?'mn-MN':'en-US', {hour:'2-digit',minute:'2-digit'});
}

function attColor(p) {
  return p >= 75 ? 'var(--success)' : p >= 50 ? 'var(--warning)' : 'var(--danger)';
}

// ── Exam mode ────────────────────────────────────────────────────────────────
async function toggleExamMode(enabled) {
  await api('POST','/api/exam_mode',{enabled});
  const navEl = document.getElementById('navExamToggle');
  if (navEl) navEl.checked = enabled;
  const wrap = document.getElementById('navExamWrap');
  if (wrap) wrap.classList.toggle('exam-on', enabled);
  toast(enabled ? '🔒 ' + t('exam_mode') + ' ON' : t('exam_mode') + ' OFF', enabled ? 'warning' : 'info');
}

// ── Push notifications ───────────────────────────────────────────────────────
async function requestNotifPerm() {
  if (!('Notification' in window)) { toast('Notifications not supported','error'); return; }
  const p = await Notification.requestPermission();
  toast(p==='granted'?'Мэдэгдэл идэвхжлээ!':'Мэдэгдэл зөвшөөрөгдөөгүй', p==='granted'?'success':'warning');
}

function pushNotif(alert) {
  const isPhone   = alert.alert_type === 'phone_detected';
  const isUnknown = alert.alert_type === 'unknown_person';
  const label     = alertLabel(alert.alert_type);
  const ts        = fmtTime(alert.timestamp);
  const msg       = `${alert.student_name} — ${label}`;

  if (Notification.permission === 'granted') {
    new Notification('Mergen AI ⚠️', { body: `${msg} @ ${ts}` });
  }

  if (isUnknown) {
    toast(`⚠️ ${t('alert_unknown')}!`, 'error');
  }

  const cls  = isPhone ? 'phone' : isUnknown ? 'unknown' : 'suspicious';
  const icol = isPhone ? 'orange' : isUnknown ? 'purple' : 'red';
  const iid  = isPhone ? 'i-phone' : isUnknown ? 'i-person-off' : 'i-alert';

  const html = `
    <div class="notif-item ${cls}">
      <div class="notif-icon-wrap ${icol}"><svg class="icon-sm"><use href="#${iid}"/></svg></div>
      <div class="notif-body">
        <strong>${alert.student_name}</strong>
        <span>${label}</span>
      </div>
      <span class="notif-time">${ts}</span>
    </div>`;

  ['teacherNotifLog','monAlertLog','adminNotifLog'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.querySelector('.text-muted')) el.innerHTML = '';
    el.insertAdjacentHTML('afterbegin', html);
  });
}

async function pollAlerts() {
  const alerts = await api('GET',`/api/alerts/recent?since_id=${S.lastAlertId}`).catch(()=>[]);
  if (!alerts.length) return;
  S.lastAlertId = Math.max(...alerts.map(a=>a.id));
  [...alerts].reverse().forEach(pushNotif);
}

function loadExistingAlerts(logs) {
  const alerts = Array.isArray(logs) ? logs : [];
  if (!alerts.length) return;
  S.lastAlertId = Math.max(...alerts.map(a=>a.id));
  const html = alerts.slice(0,20).map(a => {
    const isPhone   = a.alert_type==='phone_detected';
    const isUnknown = a.alert_type==='unknown_person';
    const icol = isPhone?'orange':isUnknown?'purple':'red';
    const iid  = isPhone?'i-phone':isUnknown?'i-person-off':'i-alert';
    const cls  = isPhone?'phone':isUnknown?'unknown':'suspicious';
    return `<div class="notif-item ${cls}">
      <div class="notif-icon-wrap ${icol}"><svg class="icon-sm"><use href="#${iid}"/></svg></div>
      <div class="notif-body"><strong>${a.student_name}</strong><span>${alertLabel(a.alert_type)}</span></div>
      <span class="notif-time">${fmtTime(a.timestamp)}</span>
    </div>`;
  }).join('');

  ['teacherNotifLog','monAlertLog','adminNotifLog'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html || `<p class="text-muted text-sm">${t('no_alerts')}</p>`;
  });
}

document.addEventListener('keydown', async e => {
  if (e.key.toLowerCase()==='p' && !e.target.matches('input,select,textarea')) {
    await api('POST','/api/alerts/phone',{}).catch(()=>{});
    toast(t('alert_phone')+'! (P key)', 'warning');
  }
});

// ═════════════════════ ENROLL ════════════════════════════════════════════════

function switchEnrollTab(tab) {
  S.captured = [null, null, null];
  if (tab !== 'cam') stopEnrollCam();
  document.getElementById('tab-cam').classList.toggle('active',   tab === 'cam');
  document.getElementById('tab-file').classList.toggle('active',  tab === 'file');
  document.getElementById('panel-cam').classList.toggle('active', tab === 'cam');
  document.getElementById('panel-file').classList.toggle('active',tab === 'file');
  for (let i=0;i<3;i++) {
    const box = document.getElementById(`prevBox${i}`);
    if (box) {
      box.classList.remove('has-img');
      box.innerHTML=`<div class="upload-ph"><svg class="icon-lg"><use href="#i-camera"/></svg><span>Зураг сонгох</span></div>`;
      const inp = document.getElementById(`imgFile${i}`);
      if (inp) inp.value='';
    }
  }
  updateUploadState();
}

async function startEnrollCam() {
  try {
    S.enrollStream = await navigator.mediaDevices.getUserMedia({video:{facingMode:'user'}});
    const vid = document.getElementById('enrollVideo');
    vid.srcObject = S.enrollStream;
    vid.style.display = 'block';
    document.getElementById('camPH').style.display = 'none';
    document.getElementById('camBox').classList.add('active');
    document.getElementById('btnCapture').disabled = false;
    document.getElementById('btnStartCam').disabled = true;
  } catch(err) { toast('Камер нээгдсэнгүй: '+err.message,'error'); }
}

function stopEnrollCam() {
  if (S.enrollStream) { S.enrollStream.getTracks().forEach(t=>t.stop()); S.enrollStream=null; }
  const vid = document.getElementById('enrollVideo');
  if (vid) { vid.style.display='none'; vid.srcObject=null; }
  const ph = document.getElementById('camPH');
  if (ph) ph.style.display='flex';
  const box = document.getElementById('camBox');
  if (box) box.classList.remove('active');
  const btnCap = document.getElementById('btnCapture');
  if (btnCap) btnCap.disabled = true;
  const btnStart = document.getElementById('btnStartCam');
  if (btnStart) btnStart.disabled = false;
}

function capturePhoto() {
  const nextSlot = S.captured.findIndex(c => !c);
  if (nextSlot === -1) return;
  const vid = document.getElementById('enrollVideo');
  const cnv = document.getElementById('captureCanvas');
  cnv.getContext('2d').drawImage(vid, 0, 0, 640, 480);
  S.captured[nextSlot] = cnv.toDataURL('image/jpeg', 0.85);
  updateUploadState();
  if (S.captured.every(Boolean)) {
    document.getElementById('btnCapture').disabled = true;
    toast('3 зураг бэлэн болсон!', 'success');
  }
}

function previewFile(idx) {
  const file = document.getElementById(`imgFile${idx}`).files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const box = document.getElementById(`prevBox${idx}`);
    box.innerHTML = `<img src="${e.target.result}" alt="">`;
    box.classList.add('has-img');
    S.captured[idx] = e.target.result;
    updateUploadState();
  };
  reader.readAsDataURL(file);
}

function updateUploadState() {
  const filled = S.captured.filter(Boolean).length;
  for (let i = 0; i < 3; i++) {
    const d = document.getElementById(`cd${i}`);
    if (S.captured[i])      { d.className='cdot done';   d.innerHTML=ico('i-check','icon-sm'); }
    else if (i === filled)  { d.className='cdot active'; d.textContent=i+1; }
    else                    { d.className='cdot';        d.textContent=i+1; }
  }
  document.getElementById('btnEnroll').disabled = filled < 3;
}

async function submitEnroll() {
  const name = document.getElementById('enrollName').value.trim();
  const cls  = document.getElementById('enrollClass').value.trim();
  const role = document.getElementById('enrollRole').value;
  const res  = document.getElementById('enrollResult');
  if (!name) { toast(t('label_name')+'?','error'); return; }
  if (S.captured.filter(Boolean).length < 3) { toast('3 зураг оруулна уу','error'); return; }

  res.innerHTML=`<span class="text-muted">${t('loading')}</span>`;
  document.getElementById('btnEnroll').disabled=true;

  try {
    const data = await api('POST','/api/enroll',{name,class_name:cls,role,images:S.captured});
    res.innerHTML=`<span style="color:var(--success);font-weight:600">${data.name} ${t('enroll_ok')} (${data.captures})</span>`;
    S.captured = [null, null, null];
    for (let i=0; i<3; i++) {
      const box = document.getElementById(`prevBox${i}`);
      if (box) { box.classList.remove('has-img'); box.innerHTML=`<div class="upload-ph"><svg class="icon-lg"><use href="#i-camera"/></svg><span>Зураг сонгох</span></div>`; }
      const inp = document.getElementById(`imgFile${i}`);
      if (inp) inp.value='';
    }
    stopEnrollCam();
    updateUploadState();
    document.getElementById('enrollName').value='';
  } catch(e) {
    res.innerHTML=`<span style="color:var(--danger)">${e.message||t('enroll_fail')}</span>`;
    document.getElementById('btnEnroll').disabled=false;
  }
}

// ═════════════════════ MONITOR ═══════════════════════════════════════════════

async function testRecognition() {
  const input = document.getElementById('testRecogFile');
  const file  = input.files[0];
  if (!file) return;
  const res = document.getElementById('testRecogResult');
  res.innerHTML = '<span class="text-muted">Шалгаж байна…</span>';
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r    = await fetch('/api/test/recognize', {method:'POST', body:fd});
    const data = await r.json();
    if (data.matched) {
      res.innerHTML = `<span style="color:var(--success);font-weight:600">✓ ${data.name} (${data.class_name}) — ${data.similarity}</span>`;
    } else {
      res.innerHTML = `<span style="color:var(--danger)">✗ ${data.reason}${data.best_sim!==undefined?' (best: '+data.best_sim+')':''}</span>`;
    }
  } catch(e) {
    res.innerHTML = `<span style="color:var(--danger)">Алдаа: ${e.message}</span>`;
  }
  input.value = '';
}

function uploadVideoFile() {
  const input = document.getElementById('videoFileInput');
  const file  = input.files[0];
  if (!file) return;

  const fd = new FormData();
  fd.append('file', file);

  const wrap    = document.getElementById('videoUploadProgress');
  const bar     = document.getElementById('videoProgressBar');
  const pct     = document.getElementById('videoProgressPct');
  const fname   = document.getElementById('videoProgressFile');
  wrap.style.display = 'block';
  bar.style.width    = '0%';
  pct.textContent    = '0%';
  fname.textContent  = file.name;
  document.getElementById('btnVideoFile').disabled = true;

  const xhr = new XMLHttpRequest();

  xhr.upload.onprogress = e => {
    if (!e.lengthComputable) return;
    const p = Math.round(e.loaded / e.total * 100);
    bar.style.width   = p + '%';
    pct.textContent   = p + '%';
  };

  xhr.onload = () => {
    wrap.style.display = 'none';
    input.value = '';
    if (xhr.status === 200) {
      const data = JSON.parse(xhr.responseText);
      document.getElementById('btnStartMon').style.display  = 'none';
      document.getElementById('btnVideoFile').style.display = 'none';
      document.getElementById('btnStopMon').style.display   = 'inline-flex';
      updateCamPill(true);
      _setVideoSrc(true);
      toast(data.filename + ' боловсруулж байна', 'success');
    } else {
      try {
        const err = JSON.parse(xhr.responseText);
        toast(err.detail || 'Алдаа гарлаа', 'error');
      } catch { toast('Алдаа гарлаа', 'error'); }
      document.getElementById('btnVideoFile').disabled = false;
    }
  };

  xhr.onerror = () => {
    wrap.style.display = 'none';
    input.value = '';
    toast('Сүлжээний алдаа', 'error');
    document.getElementById('btnVideoFile').disabled = false;
  };

  xhr.open('POST', '/api/video/upload');
  xhr.send(fd);
}

function _setVideoSrc(on) {
  const img = document.getElementById('videoStream');
  if (on) {
    img.src = '/video_feed?t=' + Date.now();
  } else {
    img.src = '';
  }
}

async function initMonitor() {
  const st = await api('GET','/api/camera/status').catch(()=>({running:false,exam_mode:false,faces:[]}));

  const navToggle = document.getElementById('navExamToggle');
  if (navToggle) navToggle.checked = st.exam_mode;
  updateCamPill(st.running);
  if (st.running) {
    document.getElementById('btnStartMon').style.display='none';
    document.getElementById('btnVideoFile').style.display='none';
    document.getElementById('btnStopMon').style.display='inline-flex';
    _setVideoSrc(true);
  } else {
    _setVideoSrc(false);
  }
  const existing = await api('GET','/api/alerts/recent?since_id=0').catch(()=>[]);
  loadExistingAlerts(existing);

  S.monTimer = setInterval(async()=>{
    const s=await api('GET','/api/camera/status').catch(()=>null);
    if (!s) return;
    renderFacePanel(s.faces);
    await pollAlerts();
    if (!s.running && document.getElementById('btnStopMon').style.display !== 'none') {
      document.getElementById('btnStartMon').style.display='inline-flex';
      document.getElementById('btnVideoFile').style.display='inline-flex';
      document.getElementById('btnVideoFile').disabled=false;
      document.getElementById('btnStopMon').style.display='none';
      document.getElementById('btnUnlock').style.display='none';
      updateCamPill(false);
      _setVideoSrc(false);
      toast('Видео дууслаа','info');
    }
  },2500);
}

async function startMonCam() {
  await api('POST','/api/camera/start').catch(e=>{ toast(e.message,'error'); throw e; });
  document.getElementById('btnStartMon').style.display='none';
  document.getElementById('btnVideoFile').style.display='none';
  document.getElementById('btnStopMon').style.display='inline-flex';
  updateCamPill(true);
  _setVideoSrc(true);
  toast(t('cam_on'),'success');
}

async function stopMonCam() {
  await api('POST','/api/camera/stop');
  document.getElementById('btnStartMon').style.display='inline-flex';
  document.getElementById('btnVideoFile').style.display='inline-flex';
  document.getElementById('btnVideoFile').disabled=false;
  document.getElementById('btnStopMon').style.display='none';
  document.getElementById('btnUnlock').style.display='none';
  updateCamPill(false);
  _setVideoSrc(false);
  toast(t('cam_off'),'info');
}

async function lockPerson(e) {
  const img  = document.getElementById('videoStream');
  if (!img.src || img.src === window.location.href) return;
  const rect = img.getBoundingClientRect();
  const nx   = (e.clientX - rect.left)  / rect.width;
  const ny   = (e.clientY - rect.top)   / rect.height;
  const res  = await api('POST', '/api/lock', { nx, ny });
  if (res && res.locked) {
    document.getElementById('btnUnlock').style.display = 'inline-flex';
    toast('Lock: #' + res.track_id, 'info');
  } else {
    toast('Хүн олдсонгүй', 'warn');
  }
}

async function unlockPerson() {
  await api('POST', '/api/unlock');
  document.getElementById('btnUnlock').style.display = 'none';
  toast('Lock суллагдлаа', 'info');
}

function updateCamPill(running) {
  const pill = document.getElementById('camPill');
  pill.className = 'cam-pill'+(running?' on':'');
  pill.innerHTML = `<span class="cam-pill-dot"></span><span>${running?t('cam_on'):t('cam_off')}</span>`;
}

function renderFacePanel(faces) {
  const el=document.getElementById('facePanel');
  if (!faces||!faces.length){ el.innerHTML=`<p class="text-muted text-sm">${t('no_faces')}</p>`; return; }
  el.innerHTML=faces.map(f=>{
    const isDown=f.looking_down;
    const led=isDown?'var(--warning)':f.attentive?'var(--success)':'#6B7280';
    const status=isDown?t('status_down'):f.attentive?t('status_att'):t('status_dist');
    const downTag=isDown?`<span class="down-indicator"><svg class="icon-sm"><use href="#i-down"/></svg>${t('alert_down')}</span>`:'';
    const uBadge = f.uniform_on === true
      ? `<span class="uniform-badge uniform-yes">${t('uniform_yes')}</span>`
      : f.uniform_on === false
        ? `<span class="uniform-badge uniform-no">${t('uniform_no')}</span>`
        : '';
    return `<div class="face-item" style="flex-wrap:wrap;gap:6px">
      <div class="face-led" style="background:${led}"></div>
      <div style="flex:1"><div class="face-item-name">${f.name||'Unknown'}</div>
        <div class="face-item-status">${status}</div></div>
      ${downTag}${uBadge}
    </div>`;
  }).join('');
}

// ═════════════════════ TEACHER DASHBOARD ═════════════════════════════════════

let attChart=null;

async function initTeacher() {
  document.getElementById('teacherDate').textContent =
    new Date().toLocaleDateString(S.lang==='mn'?'mn-MN':'en-US',
      {weekday:'long',year:'numeric',month:'long',day:'numeric'});

  const em=await api('GET','/api/exam_mode').catch(()=>({enabled:false}));
  const nt=document.getElementById('navExamToggle');
  if(nt) nt.checked=em.enabled;

  const existing=await api('GET','/api/alerts/recent?since_id=0').catch(()=>[]);
  loadExistingAlerts(existing);

  await refreshTeacher();
  S.pollTimer=setInterval(async()=>{ await refreshTeacher(); await pollAlerts(); },5000);
}

async function refreshTeacher() {
  const [att,hist,uniformToday,uniformStats]=await Promise.all([
    api('GET','/api/attendance/today'),
    api('GET','/api/attention/history'),
    api('GET','/api/uniform/today'),
    api('GET','/api/uniform/stats'),
  ]).catch(()=>[null,null,null,null]);
  if(att){ S.cachedAtt=att; renderAttTable(att); }
  if(hist) updateChart(hist);
  if(uniformStats) document.getElementById('tUniform').textContent=uniformStats.rate+'%';
  if(uniformToday){ S.cachedUniform=uniformToday; renderUniformTable(uniformToday); }
}

function renderUniformTable(rows) {
  const el = document.getElementById('uniformTable');
  if (!el) return;
  if (!rows.length) { el.innerHTML = `<p class="text-muted text-sm">${t('no_student')}</p>`; return; }
  el.innerHTML = `<div style="display:flex;flex-direction:column;gap:8px">` +
    rows.map(r => {
      const badge = r.is_wearing === true
        ? `<span class="uniform-badge uniform-yes">${t('uniform_yes')}</span>`
        : r.is_wearing === false
          ? `<span class="uniform-badge uniform-no">${t('uniform_no')}</span>`
          : `<span class="uniform-badge uniform-unk">${t('uniform_unk')}</span>`;
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <div><strong>${r.name}</strong> <span class="text-muted text-sm">${r.class_name}</span></div>
        ${badge}
      </div>`;
    }).join('') + `</div>`;
}

function renderAttTable(rows) {
  const present=rows.filter(r=>r.present).length;
  const absent=rows.length-present;
  const alerts=rows.reduce((s,r)=>s+r.alert_count,0);
  const pRows=rows.filter(r=>r.present);
  const avgAtt=pRows.length?Math.round(pRows.reduce((s,r)=>s+r.attention_score,0)/pRows.length):0;

  setStatVal('tPresent', present);
  setStatVal('tAbsent',  absent);
  setStatVal('tAtten',   avgAtt, '%');
  setStatVal('tAlerts',  alerts);

  const tbody=document.getElementById('attTable');
  if(!rows.length){tbody.innerHTML=`<tr><td colspan="6" class="text-muted">${t('no_student')}</td></tr>`;return;}

  tbody.innerHTML=rows.map(r=>{
    const c=attColor(r.attention_score);
    const sb=r.present
      ?`<span class="badge badge-green"><svg class="icon-sm"><use href="#i-check"/></svg>${t('badge_present')}</span>`
      :`<span class="badge badge-gray">${t('badge_absent')}</span>`;
    const ab=r.alert_count>0
      ?`<span class="badge badge-red"><svg class="icon-sm"><use href="#i-alert"/></svg>${r.alert_count}</span>`
      :`<span style="color:var(--muted)">—</span>`;
    const uRow = S.cachedUniform ? S.cachedUniform.find(u=>u.id===r.id) : null;
    const ub = uRow
      ? (uRow.is_wearing === true
          ? `<span class="uniform-badge uniform-yes">${t('uniform_yes')}</span>`
          : uRow.is_wearing === false
            ? `<span class="uniform-badge uniform-no">${t('uniform_no')}</span>`
            : `<span class="uniform-badge uniform-unk">${t('uniform_unk')}</span>`)
      : `<span class="uniform-badge uniform-unk">${t('uniform_unk')}</span>`;
    return `<tr>
      <td><strong>${r.name}</strong><br><span class="text-muted" style="font-size:.75rem">${r.class_name}</span></td>
      <td><span style="font-size:.84rem;display:flex;align-items:center;gap:5px"><svg class="icon-sm" style="color:var(--muted)"><use href="#i-clock"/></svg>${fmtTime(r.arrived_at)}</span></td>
      <td>
        <div class="att-wrap">
          <div class="att-track"><div class="att-fill" style="width:${r.attention_score}%;background:${c}"></div></div>
          <span class="att-pct" style="color:${c}">${r.attention_score}%</span>
        </div>
      </td>
      <td>${ab}</td><td>${sb}</td><td>${ub}</td>
    </tr>`;
  }).join('');
}

function updateChart(hist) {
  const labels=hist.map(h=>h.time_label);
  const data=hist.map(h=>h.avg_attention);

  if (!attChart) {
    const ctx=document.getElementById('attChart').getContext('2d');
    Chart.defaults.font.family="'Outfit', sans-serif";
    Chart.defaults.color='#6B7280';
    attChart=new Chart(ctx,{
      type:'line',
      data:{
        labels,
        datasets:[{
          label:t('stat_avg_att'),
          data,
          borderColor:'#15803D',
          backgroundColor:'rgba(21,128,61,.08)',
          fill:true,
          tension:0.45,
          pointRadius:4,
          pointBackgroundColor:'#15803D',
          pointBorderColor:'#fff',
          pointBorderWidth:2,
        }]
      },
      options:{
        responsive:true, animation:false,
        scales:{
          y:{ min:0, max:100,
              grid:{color:'#E8ECF4'},
              ticks:{color:'#9CA3AF',callback:v=>v+'%'}},
          x:{ grid:{color:'#E8ECF4'},
              ticks:{color:'#9CA3AF',maxTicksLimit:10}}
        },
        plugins:{
          legend:{labels:{color:'#374151',boxWidth:12,usePointStyle:true}},
          tooltip:{
            backgroundColor:'#15803D',
            callbacks:{label:ctx=>' '+ctx.parsed.y+'%'}
          }
        }
      }
    });
  } else {
    attChart.data.labels=labels;
    attChart.data.datasets[0].data=data;
    attChart.data.datasets[0].label=t('stat_avg_att');
    attChart.update('none');
  }
}

// ═════════════════════ PARENT DASHBOARD ══════════════════════════════════════

async function initParent() {
  const [res, uniformRows, histRows]=await Promise.all([
    api('GET','/api/parent/student').catch(()=>null),
    api('GET','/api/uniform/today').catch(()=>[]),
    api('GET','/api/parent/history').catch(()=>[]),
  ]);
  if(!res){
    document.getElementById('pName').textContent=t('no_student');
    document.getElementById('pSummary').textContent='—';
    document.getElementById('pUniform').textContent='—';
    document.getElementById('pYesterday').textContent='—';
    document.getElementById('pHistory').textContent='—';
    return;
  }
  const s=res.student, d=res.today;

  const uRow = Array.isArray(uniformRows) ? uniformRows.find(u=>u.id===s.id) : null;
  const pUniformEl = document.getElementById('pUniform');
  if (pUniformEl) {
    if (uRow && uRow.is_wearing === true) {
      pUniformEl.innerHTML = `<span class="uniform-badge uniform-yes">${t('uniform_yes')}</span>`;
    } else if (uRow && uRow.is_wearing === false) {
      pUniformEl.innerHTML = `<span class="uniform-badge uniform-no">${t('uniform_no')}</span>`;
    } else {
      pUniformEl.innerHTML = `<span class="uniform-badge uniform-unk">${t('uniform_unk')}</span>`;
    }
  }
  document.getElementById('pName').textContent=s.name;
  document.getElementById('pClass').textContent=s.class_name;

  if(d){
    const c=attColor(d.attention_score);
    document.getElementById('pStatus').innerHTML=d.present
      ?`<span class="badge badge-green"><svg class="icon-sm"><use href="#i-check"/></svg>${t('p_present')}</span>`
      :`<span class="badge badge-gray">${t('p_absent')}</span>`;
    document.getElementById('pAttVal').textContent=d.attention_score+'%';
    document.getElementById('pAttVal').style.color=c;
    document.getElementById('pAttBar').innerHTML=`<div class="att-wrap"><div class="att-track" style="height:10px"><div class="att-fill" style="width:${d.attention_score}%;background:${c};height:10px"></div></div></div>`;
    document.getElementById('pSummary').innerHTML=`
      <div style="display:flex;flex-direction:column;gap:10px">
        <div class="flex gap8 items-center"><svg class="icon-sm" style="color:var(--muted)"><use href="#i-clock"/></svg><span>${t('p_arrived')} <strong>${fmtTime(d.arrived_at)}</strong></span></div>
        <div class="flex gap8 items-center"><svg class="icon-sm" style="color:var(--muted)"><use href="#i-alert"/></svg><span>${t('p_alerts')} <strong>${d.alert_count}</strong></span></div>
        <div class="flex gap8 items-center"><svg class="icon-sm" style="color:var(--muted)"><use href="#i-eye"/></svg><span>${t('stat_avg_att')}: <strong style="color:${c}">${d.attention_score}%</strong></span></div>
      </div>`;
  } else {
    document.getElementById('pStatus').innerHTML=`<span class="badge badge-gray">${t('badge_absent')}</span>`;
    document.getElementById('pSummary').textContent=t('badge_absent');
  }

  const hist = Array.isArray(histRows) ? histRows : [];
  const yesterday = hist.find(r => r.days_ago === 1) || null;
  const pYestEl = document.getElementById('pYesterday');
  if (yesterday) {
    const yc = attColor(yesterday.attention_score||0);
    pYestEl.innerHTML = yesterday.present
      ? `<div style="display:flex;flex-direction:column;gap:8px">
          <span class="badge badge-green"><svg class="icon-sm"><use href="#i-check"/></svg>${t('hist_present')}</span>
          <div class="flex gap8 items-center text-sm"><svg class="icon-sm" style="color:var(--muted)"><use href="#i-clock"/></svg><span>${t('p_arrived')} <strong>${fmtTime(yesterday.arrived_at)}</strong></span></div>
          <div class="flex gap8 items-center text-sm"><svg class="icon-sm" style="color:var(--muted)"><use href="#i-eye"/></svg><span>${t('stat_avg_att')}: <strong style="color:${yc}">${yesterday.attention_score||0}%</strong></span></div>
        </div>`
      : `<span class="badge badge-gray">${t('hist_absent')}</span>`;
  } else {
    pYestEl.textContent = t('hist_no_data');
  }

  const pHistEl = document.getElementById('pHistory');
  const histItems = hist.filter(r => r.days_ago >= 1).slice(0,14);
  if (histItems.length) {
    pHistEl.innerHTML = `<div style="display:flex;flex-direction:column;gap:6px">` +
      histItems.map(r => {
        const hc = attColor(r.attention_score||0);
        const label = r.days_ago === 1 ? t('yesterday_att') : r.date || `${r.days_ago}d ago`;
        return `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
          <span class="text-sm" style="font-weight:600;min-width:90px">${label}</span>
          <span class="badge ${r.present?'badge-green':'badge-gray'}" style="font-size:.72rem">${r.present?t('hist_present'):t('hist_absent')}</span>
          ${r.present?`<span class="text-sm" style="color:${hc};font-weight:700;min-width:46px;text-align:right">${r.attention_score||0}%</span>`:'<span style="min-width:46px"></span>'}
        </div>`;
      }).join('') + `</div>`;
  } else {
    pHistEl.textContent = t('hist_no_data');
  }
}

// ═════════════════════ STUDENTS PAGE ═════════════════════════════════════════

let _allStudents = [];
let _pendingDeleteId = null;

async function initStudents() {
  _allStudents = await api('GET', '/api/students').catch(() => []);
  renderStudentSummary(_allStudents);
  filterStudents();
  applyI18n();
}

function renderStudentSummary(rows) {
  const total     = rows.length;
  const withFace  = rows.filter(r => r.has_face).length;
  const present   = rows.filter(r => r.present_today).length;
  document.getElementById('stuSummary').innerHTML = `
    <span class="chip"><svg class="icon-sm"><use href="#i-users"/></svg>${t('stu_total')}: <strong>${total}</strong></span>
    <span class="chip" style="background:rgba(5,150,105,.09);color:var(--success)">
      <svg class="icon-sm"><use href="#i-check"/></svg>${t('stu_with_face')}: <strong>${withFace}</strong></span>
    <span class="chip" style="background:var(--accent-lt);color:var(--accent)">
      <svg class="icon-sm"><use href="#i-eye"/></svg>${t('stu_present')}: <strong>${present}</strong></span>`;
}

function filterStudents() {
  const q    = (document.getElementById('stuSearch')?.value || '').toLowerCase();
  const role = document.getElementById('stuRoleFilter')?.value || '';
  const face = document.getElementById('stuFaceFilter')?.value || '';

  const filtered = _allStudents.filter(s => {
    if (q    && !s.name.toLowerCase().includes(q)) return false;
    if (role && s.role !== role)                    return false;
    if (face === '1' && !s.has_face)                return false;
    if (face === '0' &&  s.has_face)                return false;
    return true;
  });
  renderStudentTable(filtered);
}

function renderStudentTable(rows) {
  const tbody = document.getElementById('stuTbody');
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:36px;color:var(--muted)">${t('no_student')}</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((s, i) => {
    const faceBadge = s.has_face
      ? `<span class="badge badge-green"><svg class="icon-sm"><use href="#i-check"/></svg>${t('face_yes')}</span>`
      : `<span class="badge badge-gray">${t('face_no')}</span>`;
    const statusBadge = s.present_today
      ? `<span class="badge badge-green">${t('badge_present')}</span>`
      : `<span class="badge badge-gray">${t('badge_absent')}</span>`;
    const roleBadge = s.role === 'teacher'
      ? `<span class="badge badge-blue">${t('role_teacher_opt')}</span>`
      : `<span class="badge badge-gray">${t('role_student')}</span>`;
    const attColor_ = attColor(s.attention_score);
    const attVal = s.present_today
      ? `<span style="font-weight:700;color:${attColor_}">${s.attention_score}%</span>`
      : `<span style="color:var(--muted)">—</span>`;
    const createdDate = s.created_at
      ? new Date(s.created_at).toLocaleDateString(S.lang==='mn'?'mn-MN':'en-US',{year:'numeric',month:'short',day:'numeric'})
      : '—';

    return `<tr>
      <td style="color:var(--muted);font-size:.8rem">${i+1}</td>
      <td>
        <div style="display:flex;align-items:center;gap:10px">
          <div style="width:36px;height:36px;border-radius:10px;background:var(--accent-lt);color:var(--accent);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.9rem;flex-shrink:0">
            ${s.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <div style="font-weight:600">${s.name}</div>
            ${s.alert_count_today > 0
              ? `<span style="font-size:.72rem;color:var(--danger)">&#9679; ${s.alert_count_today} ${t('stat_alerts').toLowerCase()}</span>`
              : ''}
          </div>
        </div>
      </td>
      <td>${s.class_name}</td>
      <td>${roleBadge}</td>
      <td>${faceBadge}</td>
      <td>${statusBadge}</td>
      <td>${attVal}</td>
      <td style="font-size:.82rem;color:var(--muted)">${createdDate}</td>
      <td style="text-align:right">
        <div style="display:flex;gap:6px;justify-content:flex-end">
          <a href="/enroll" onclick="go(event,'/enroll')">
            <button class="btn btn-ghost btn-sm" title="${t('btn_new_student')}">
              <svg class="icon-sm"><use href="#i-camera"/></svg>
            </button>
          </a>
          <button class="btn btn-sm" style="background:#FEE2E2;color:var(--danger);border:1px solid #FECACA"
                  onclick="openDeleteModal(${s.id},'${s.name.replace(/'/g,"\\'")}')">
            <svg class="icon-sm"><use href="#i-alert"/></svg>
            <span data-i18n="btn_delete">${t('btn_delete')}</span>
          </button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

function openDeleteModal(id, name) {
  _pendingDeleteId = id;
  document.getElementById('delStudentName').textContent = name;
  const modal = document.getElementById('deleteModal');
  modal.style.display = 'flex';
  applyI18n();
}

function closeDeleteModal() {
  _pendingDeleteId = null;
  document.getElementById('deleteModal').style.display = 'none';
}

async function confirmDelete() {
  if (!_pendingDeleteId) return;
  try {
    await api('DELETE', `/api/students/${_pendingDeleteId}`);
    closeDeleteModal();
    toast(S.lang==='mn'?'Оюутан устгагдлаа':'Student deleted', 'success');
    _allStudents = await api('GET', '/api/students');
    renderStudentSummary(_allStudents);
    filterStudents();
  } catch(e) {
    toast(e.message, 'error');
    closeDeleteModal();
  }
}

document.getElementById('deleteModal')?.addEventListener('click', function(e) {
  if (e.target === this) closeDeleteModal();
});

// ── Clear alert log ────────────────────────────────────────────────────────────
function clearAlertLog(logId) {
  const el = document.getElementById(logId);
  if (el) el.innerHTML = `<p class="text-muted text-sm">${t('no_alerts')}</p>`;
}

// ── Count-up animation ─────────────────────────────────────────────────────────
function animateCount(el, target, suffix='', duration=700) {
  const isNum = !isNaN(parseFloat(target));
  if (!isNum) { el.textContent = target; return; }
  const end = parseFloat(target);
  const start = 0;
  const startTime = performance.now();
  const step = (now) => {
    const p = Math.min((now - startTime) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    const val = start + (end - start) * ease;
    el.textContent = (Number.isInteger(end) ? Math.round(val) : val.toFixed(1)) + suffix;
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function setStatVal(id, value, suffix='') {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.animation = 'none';
  void el.offsetWidth;
  el.style.animation = '';
  const raw = String(value).replace(/[^0-9.]/g,'');
  const suf = String(value).replace(/[0-9.]/g,'') + suffix;
  animateCount(el, raw || value, suf);
}

// ═════════════════════ RESET ══════════════════════════════════════════════════

async function resetDemo() {
  const msg = S.lang==='mn'
    ? 'Өнөөдрийн demo өгөгдлийг устгах уу?'
    : "Reset today's demo data?";
  if (!confirm(msg)) return;
  await api('POST','/api/reset');
  if (attChart) { attChart.destroy(); attChart=null; }
  S.cachedAtt=null; S.lastAlertId=0;
  toast(S.lang==='mn'?'Demo дахилт хийгдлээ':'Demo data reset','success');
  showPage(window.location.pathname);
}

// ═════════════════════ BOOT ═══════════════════════════════════════════════════

applyI18n();
updateNav();
loadUser().then(() => {
  const path = window.location.pathname;
  if (!S.user) {
    history.replaceState({}, '', '/landing');
    showPage('/landing');
    return;
  }
  const role = S.user.role;
  const dash = role === 'admin' ? '/monitor' : role === 'parent' ? '/dashboard/parent' : '/dashboard/teacher';
  const authPages = ['/', '', '/landing', '/login', '/signup', '/about'];
  if (authPages.includes(path)) {
    history.replaceState({}, '', dash);
    showPage(dash);
  } else {
    showPage(path);
  }
});
