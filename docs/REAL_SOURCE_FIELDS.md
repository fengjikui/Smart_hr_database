# 真实人员宽表：中英文字段对照

更新：2026-09-14。来源为本地原始资料 `infomations/字段说明.md`。

按两段原始清单的出现顺序逐项配对，仅移除空行和首尾空白。中文 263 项、英文 263 项，英文标识符唯一数为 263；未删除重复中文名称，未按名称重新排序。机械对齐不等于已确认所有字段的业务含义。

当前接入约定：PostgreSQL；暂按一人一行的人员当前宽表；`person_id` 为主键；`employee_no` 为保留前导零的工号；直接主管、部门主管和部门 HRBP 的 ID 暂关联本表 `person_id`；`employee_id` 本阶段忽略；不保留历史任职和汇报线。

本表只整理源字段，不代表已经接入演示系统或开放全部字段查询。物理表名、数据类型和加工公式尚未提供。权限及历史查询边界见 [真实数据接入约定](REAL_SOURCE_CONTRACT.md)。

| 序号 | 中文字段名 | 英文字段名 | 已确认约定或待核对事项 |
| --- | --- | --- | --- |
| 1 | 人员id | `person_id` | 已确认：人员主键；暂按一名员工一行。物理类型待确认。 |
| 2 | 工号 | `employee_no` | 已确认：工号；按标识符处理并保留前导零，例如 00031266。 |
| 3 | 姓名 | `name` |  |
| 4 | 拼音名 | `employee_pinyin_name` |  |
| 5 | 英文名 | `employee_en_name` |  |
| 6 | 曾用名 | `former_name` |  |
| 7 | 性别编码 | `sex_code` |  |
| 8 | 性别 | `sex_code_desc` |  |
| 9 | 常驻地 | `base_city_name` |  |
| 10 | 调入常驻地时间 | `base_city_date` |  |
| 11 | 出生日期 | `birth_date` |  |
| 12 | 年龄 | `age` | 年龄字段；计算基准日和与出生日期的一致性待确认。 |
| 13 | 档案出生日期 | `file_birth_date` |  |
| 14 | 到期日期(身份证信息) | `expired_date` |  |
| 15 | 签发日期(身份证信息) | `sign_date` |  |
| 16 | 政治面貌 | `political_outlook` |  |
| 17 | 加入党日期 | `join_party_date` |  |
| 18 | 国际编码 | `national_code` |  |
| 19 | 国籍 | `national_code_desc` |  |
| 20 | 籍贯编码 | `home_town_code` |  |
| 21 | 籍贯 | `home_town_code_desc` |  |
| 22 | 民族编码 | `folk_code` |  |
| 23 | 民族 | `folk_code_desc` |  |
| 24 | 婚姻状况编码 | `marry_status_code` |  |
| 25 | 婚姻状况 | `marry_status_code_desc` |  |
| 26 | 健康状况 | `health_info` |  |
| 27 | 院校国家 | `school_national_name` |  |
| 28 | 院校名称 | `school_name` |  |
| 29 | 学历编码 | `diploma_code` |  |
| 30 | 学历 | `diploma_code_desc` |  |
| 31 | 学位编码 | `degree_code` |  |
| 32 | 学位 | `degree_code_desc` |  |
| 33 | 第一专业 | `first_major` |  |
| 34 | 第二专业 | `second_major` |  |
| 35 | 是否第一学历 | `first_diploma_flag` | 是否第一学历；不自动解释为最高学历标志。 |
| 36 | 是否全日制 | `full_time_flag` |  |
| 37 | 开始日期(教育经历信息) | `education_begin_date` |  |
| 38 | 结束日期(教育经历信息) | `education_expired_date` | 原始中文为教育经历结束日期；是否等于毕业日期待确认。 |
| 39 | 招聘类型编码 | `hire_type_code` |  |
| 40 | 招聘类型 | `hire_type_code_desc` |  |
| 41 | 招聘原因编码 | `hire_cause_code` |  |
| 42 | 招聘原因 | `hire_cause_code_desc` |  |
| 43 | 招聘来源 | `hire_source` |  |
| 44 | 用工类型编码 | `labour_type_code` |  |
| 45 | 用工类型 | `labour_type_code_desc` |  |
| 46 | 用工状态编码 | `labour_status_code` |  |
| 47 | 用工状态 | `labour_status_code_desc` |  |
| 48 | 用工国家 | `labour_country_name` |  |
| 49 | 司龄开始日期 | `first_begin_date` |  |
| 50 | 入职日期 | `onboard_date` | 原始中文为入职日期；与加入集团、加入公司及首次入职日期的业务区别待确认。 |
| 51 | 入职类型编码 | `recruiting_type_code` |  |
| 52 | 入职类型 | `recruiting_type_code_desc` |  |
| 53 | 入职原因编码 | `recruiting_cause_code` |  |
| 54 | 入职原因 | `recruiting_cause_code_desc` |  |
| 55 | 加入集团日期 | `join_group_date` | 加入集团日期；不自动视为当前公司入职日期。 |
| 56 | 加入公司日期(调入当前子公司时间) | `join_company_date` | 原始中文说明为调入当前子公司时间。 |
| 57 | 参加工作日期 | `job_date` |  |
| 58 | 工作状态编码 | `work_state_code` |  |
| 59 | 工作状态 | `work_state_code_desc` |  |
| 60 | 零级部门编码 | `l0_dept_code` |  |
| 61 | 零级部门名称 | `l0_dept_cn_name` |  |
| 62 | 一级部门编码 | `l1_dept_code` |  |
| 63 | 一级部门名称 | `l1_dept_cn_name` |  |
| 64 | 二级部门编码 | `l2_dept_code` |  |
| 65 | 二级部门名称 | `l2_dept_cn_name` |  |
| 66 | 三级部门编码 | `l3_dept_code` |  |
| 67 | 三级部门名称 | `l3_dept_cn_name` |  |
| 68 | 四级部门编码 | `l4_dept_code` |  |
| 69 | 四级部门名称 | `l4_dept_cn_name` |  |
| 70 | 五级部门编码 | `l5_dept_code` |  |
| 71 | 五级部门名称 | `l5_dept_cn_name` |  |
| 72 | 最小部门编码 | `dept_code` |  |
| 73 | 最小部门名称 | `dept_cn_name` |  |
| 74 | 调入最小部门生效时间 | `dept_join_date` |  |
| 75 | 部门主管id | `dept_master_id` | 按本次约定关联本表 person_id；是否独立形成部门授权尚未确认。 |
| 76 | 部门主管 | `dept_master_name` | 部门主管展示名称；真实案例中的不同取值仍待解释。 |
| 77 | 部门HRBPid | `dept_hrbp_id` | 已确认：部门 HRBP，暂关联本表 person_id；HRBP 服务范围依据。 |
| 78 | 部门HRBP | `dept_hrbp_name` | 部门 HRBP 展示名称；关联使用 dept_hrbp_id。 |
| 79 | 岗位编码 | `position_code` |  |
| 80 | 岗位 | `position_code_desc` |  |
| 81 | 岗位分类 | `position_class` |  |
| 82 | 职务编码 | `job_code` |  |
| 83 | 职务 | `job_code_desc` |  |
| 84 | 职级编码 | `joblevel_code` |  |
| 85 | 职级 | `joblevel_code_desc` |  |
| 86 | 职等编码 | `joblevel_type_code` |  |
| 87 | 职等 | `joblevel_type_code_desc` |  |
| 88 | 直接主管id | `head_person_id` | 已确认：直接主管，暂关联本表 person_id；管理线递归依据。 |
| 89 | 直接主管 | `head_person_name` | 直接主管展示名称；关联使用 head_person_id。 |
| 90 | 任命族 | `appointed_clan` |  |
| 91 | 任命类 | `appointed_class` |  |
| 92 | 任命子类 | `appointed_sub_class` |  |
| 93 | 任命名称（专业任命） | `appointed_name` |  |
| 94 | 任命职级 | `appointed_job_level` |  |
| 95 | 任命的本地名称 | `appointed_local_name` |  |
| 96 | 任命补充信息 | `appointed_supplement` |  |
| 97 | 专业岗位任命日期 | `prof_pos_appoint_date` |  |
| 98 | 专业岗位任命发布部门 | `prof_pos_appoint_release_dept` |  |
| 99 | 任命岗位要求的任职资格 | `appointment_position_qualifications` |  |
| 100 | 是否有管理者任命 | `manager_appointed_flag` |  |
| 101 | 管理者任命 | `appointment_managers` |  |
| 102 | 管理者任命职级 | `managerial_appointment_rank` |  |
| 103 | 管理者任命时间 | `appointment_manager_date` |  |
| 104 | 管理岗本岗名称 | `management_position_name` |  |
| 105 | 管理岗岗位群 | `management_position_group` |  |
| 106 | 任命管理者对应的正职岗位职级 | `appoint_manager_positions_ranks` |  |
| 107 | 人岗匹配结果 | `job_matching_results` |  |
| 108 | 上次人岗匹配情况 | `last_person_job_matching_situation` |  |
| 109 | 上次人岗匹配时间 | `last_person_job_matching_date` |  |
| 110 | 个人职级变动记录1 | `personal_rank_change_record_1` |  |
| 111 | 个人职级变动时间1 | `personal_rank_change_date_1` |  |
| 112 | 个人职级变动记录2 | `personal_rank_change_record_2` |  |
| 113 | 个人职级变动时间2 | `personal_rank_change_date_2` |  |
| 114 | 个人职级变动记录3 | `personal_rank_change_record_3` |  |
| 115 | 个人职级变动时间3 | `personal_rank_change_date_3` |  |
| 116 | 个人职级变动记录4 | `personal_rank_change_record_4` |  |
| 117 | 个人职级变动时间4 | `personal_rank_change_date_4` |  |
| 118 | 当前任职开始日期 | `current_employment_start_date` |  |
| 119 | 当前任职累计天数 | `current_employment_accumulated_days` |  |
| 120 | 当前人岗开始日期 | `current_job_start_date` |  |
| 121 | 当前人岗累计天数 | `current_job_accumulated_days` |  |
| 122 | 近三次绩效 | `three_count_achievement` |  |
| 123 | 近三年绩效 | `three_year_achievement` |  |
| 124 | 近五次绩效 | `five_count_achievement` |  |
| 125 | 近五年绩效 | `five_year_achievement` |  |
| 126 | 转正状态 | `conversion_status` |  |
| 127 | 转正综评等级 | `regularizatione_evaluation_level` |  |
| 128 | 转正时间 | `confirmation_date` |  |
| 129 | 近一次绩效结果 | `last_achievement_result_name` |  |
| 130 | 任职资格1生效日期 | `qualification_1_effective_date` |  |
| 131 | 任职资格1失效日期 | `qualification_1_expiration_date` |  |
| 132 | 任职资格1族 | `qualification_for_position_1` |  |
| 133 | 任职资格1类 | `qualification_category_1` |  |
| 134 | 任职资格1子类 | `qualification_subclass_1` |  |
| 135 | 任职资格1级 | `qualification_level_1` |  |
| 136 | 任职资格1等 | `qualification_topnotch_1` |  |
| 137 | 任职资格1支持的职级 | `qualification_1_job_positions_supported` |  |
| 138 | 任职资格1是否延期 | `qualification_1_extended_flag` |  |
| 139 | 任职资格1族类是否与当前岗位匹配 | `qualification_1_group_match_current_position` |  |
| 140 | 任职资格2生效日期 | `qualification_2_effective_date` |  |
| 141 | 任职资格2失效日期 | `qualification_2_expiration_date` |  |
| 142 | 任职资格2族 | `qualification_for_position_2` |  |
| 143 | 任职资格2类 | `qualification_category_2` |  |
| 144 | 任职资格2子类 | `qualification_subclass_2` |  |
| 145 | 任职资格2级 | `qualification_level_2` |  |
| 146 | 任职资格2等 | `qualification_topnotch_2` |  |
| 147 | 任职资格2支持的职级 | `qualification_2_job_positions_supported` |  |
| 148 | 任职资格2是否延期 | `qualification_2_extended_flag` |  |
| 149 | 签约公司编码(当前子公司) | `contract_company_code` |  |
| 150 | 签约公司(当前子公司) | `contract_company_code_desc` |  |
| 151 | 合同类型编码 | `contract_type_code` |  |
| 152 | 合同类型 | `contract_type_code_desc` |  |
| 153 | 合同开始日期 | `contract_start_date` |  |
| 154 | 合同结束日期 | `contract_end_date` |  |
| 155 | 参保地 | `social_insure_local` |  |
| 156 | 协议工作地名称 | `agreement_workplace_name` |  |
| 157 | 职位开始日期 | `position_start_date` |  |
| 158 | 职位编码 | `job_position_code` |  |
| 159 | 职位族 | `position_family` |  |
| 160 | 职位类 | `job_category` |  |
| 161 | 职位子类 | `job_subclass` |  |
| 162 | 职位名称 | `job_title` |  |
| 163 | 职位职级 | `position_rank` |  |
| 164 | 试用期天数 | `probationary_period_days` |  |
| 165 | 试用期结果 | `trial_period_results` |  |
| 166 | 试用期开始日期 | `trial_period_start_date` |  |
| 167 | 试用期转正日期 | `trial_period_end_date` |  |
| 168 | 离职日期 | `termin_date` | 离职日期；离职人员是否保留在宽表中待确认。 |
| 169 | 离职类型编码 | `resignation_type` | 按原文位置对照为离职类型编码；英文名与相邻列不直观，保留原顺序待核对。 |
| 170 | 离职类型 | `resignation_type_code` | 按原文位置对照为离职类型；不自行交换两列映射。 |
| 171 | 离职原因编码 | `termination_cause_code` |  |
| 172 | 离职原因 | `termination_cause_code_desc` |  |
| 173 | 本年度绩效结果 | `curr_year_perfo` |  |
| 174 | 本年度半年绩效结果 | `curr_year_h1_perfo` |  |
| 175 | 本年度季度绩效结果 | `curr_year_q_perfo` |  |
| 176 | 本年度劳动态度 | `curr_year_labor_attitude` |  |
| 177 | 上年度绩效结果 | `last_year_perfo` |  |
| 178 | 上年度半年绩效结果 | `last_year_h1_perfo` |  |
| 179 | 上年度季度绩效结果 | `last_year_q_perfo` |  |
| 180 | 上年度劳动态度 | `last_year_labor_attitude` |  |
| 181 | 上上年度绩效结果 | `last2_year_perfo` |  |
| 182 | 上上年度半年绩效结果 | `last2_year_h1_perfo` |  |
| 183 | 上上年度季度绩效结果 | `last2_year_q_perfo` |  |
| 184 | 上上年度劳动态度 | `last2_year_labor_attitude` |  |
| 185 | 上上上年度绩效结果 | `last3_year_perfo` |  |
| 186 | 上上上年度半年绩效结果 | `last3_year_h1_perfo` |  |
| 187 | 上上上年度季度绩效结果 | `last3_year_q_perfo` |  |
| 188 | 上上上年度劳动态度 | `last3_year_labor_attitude` |  |
| 189 | 业务属性(行业线) | `industry_line` |  |
| 190 | 出生日期-dec | `birth_date_dec` |  |
| 191 | 公司编码 | `company_code` |  |
| 192 | 公司名称 | `company_name` |  |
| 193 | 合作方 | `partner` |  |
| 194 | 服务公司编码 | `server_company_code` |  |
| 195 | 服务公司名称 | `server_company_name` |  |
| 196 | 考勤主体 | `attendance_scheme` |  |
| 197 | 考勤主体名称 | `attendance_scheme_name` |  |
| 198 | 班次 | `work_shift_code` |  |
| 199 | 班次名称 | `work_shift_name` |  |
| 200 | 打卡方式编码 | `clock_in_mode_code` |  |
| 201 | 打卡方式 | `clock_in_mode_name` |  |
| 202 | 发薪主体 | `contract_company_name` |  |
| 203 | 电话 | `contact_no` |  |
| 204 | 证件类型 | `percretype_code` |  |
| 205 | 证件类型名称 | `percretype_code_desc` |  |
| 206 | 证件号码 | `percre_no` |  |
| 207 | 发薪银行 | `sub_branch_code` |  |
| 208 | 发薪行卡号 | `bank_account` |  |
| 209 | 开户人姓名 | `account_name` |  |
| 210 | 银行卡所在地 | `account_location` |  |
| 211 | 银行卡所在地详细 | `account_location_detail` |  |
| 212 | 最近一次绩效考评周期名称 | `last_achievement_range` |  |
| 213 | 项目归属 | `project_attribution` |  |
| 214 | 本年度Q4绩效 | `curr_year_q4_perfo` |  |
| 215 | 本年度Q3绩效 | `curr_year_q3_perfo` |  |
| 216 | 本年度Q2绩效 | `curr_year_q2_perfo` |  |
| 217 | 本年度Q1绩效 | `curr_year_q1_perfo` |  |
| 218 | 上年度Q4绩效 | `last_year_q4_perfo` |  |
| 219 | 上年度Q3绩效 | `last_year_q3_perfo` |  |
| 220 | 上年度Q2绩效 | `last_year_q2_perfo` |  |
| 221 | 上年度Q1绩效 | `last_year_q1_perfo` |  |
| 222 | 派遣开始日期 | `dispatch_start_date` |  |
| 223 | 派遣结束日期 | `dispatch_end_date` |  |
| 224 | 派遣国家 | `dispatch_country` |  |
| 225 | 派遣城市 | `dispatch_city` |  |
| 226 | 当前派遣身份（是/否） | `dispatch_flag` |  |
| 227 | 证件号码-dec | `percre_no_dec` |  |
| 228 | 联系号码-dec | `contact_no_dec` |  |
| 229 | 发薪行卡号-dec | `bank_account_dec` |  |
| 230 | 岗位类型开始时间 | `position_class_start_date` |  |
| 231 | 任命角色1 | `appointed_roles` |  |
| 232 | 任命部门名称1 | `appointed_dept_name` |  |
| 233 | 任命角色1开始时间 | `appointed_roles_start_date` |  |
| 234 | 任命角色1结束时间 | `appointed_roles_end_date` |  |
| 235 | 任命角色2 | `appointed_roles2` |  |
| 236 | 任命部门名称2 | `appointed_dept_name2` |  |
| 237 | 任命角色2开始时间 | `appointed_roles2_start_date` |  |
| 238 | 任命角色2结束时间 | `appointed_roles2_end_date` |  |
| 239 | 是否已转正 | `formalize_flag` |  |
| 240 | 最新标识 | `latest_flag` | 原表字段保留；本阶段已按一人一条当前记录处理，不凭此列推断历史版本。 |
| 241 | 企业人ID | `employee_id` | 本阶段忽略，不参与身份关联或授权计算。 |
| 242 | 绩效考核类型 | `perfo_type` |  |
| 243 | 去年月度绩效结果(由近及远) | `last_year_month_perfo` |  |
| 244 | 本年Q4月度绩效结果(由近及远) | `curr_year_q4_month_perfo` |  |
| 245 | 本年Q3月度绩效结果(由近及远) | `curr_year_q3_month_perfo` |  |
| 246 | 本年Q2月度绩效结果(由近及远) | `curr_year_q2_month_perfo` |  |
| 247 | 本年Q1月度绩效结果(由近及远) | `curr_year_q1_month_perfo` |  |
| 248 | 离职补偿起始日期 | `leave_compst_start_date` |  |
| 249 | 最近一次绩效考核时间区间 | `last_achievement_start_end` |  |
| 250 | 奖金账户银行 | `bonus_bank_name` |  |
| 251 | 奖金账户行卡号 | `bonus_bank_account` |  |
| 252 | 奖金账户开户人姓名 | `bonus_bank_account_name` |  |
| 253 | 奖金账户银行卡所在地 | `bonus_bank_account_location` |  |
| 254 | 奖金账户银行卡所在地详细 | `bonus_bank_sub_branch_name` |  |
| 255 | 奖金账户行卡号-dec | `bonus_bank_account_dec` |  |
| 256 | 任命族 | `appointed_clan1` |  |
| 257 | 任命类 | `appointed_class1` |  |
| 258 | 任命子类 | `appointed_sub_class1` |  |
| 259 | 任命名称（专业任命） | `appointed_name1` |  |
| 260 | 任命职级 | `appointed_job_level1` |  |
| 261 | 专业岗位任命日期 | `prof_pos_appoint_date1` |  |
| 262 | 专业岗位任命发布部门 | `prof_pos_appoint_release_dept1` |  |
| 263 | 公司首次入职时间 | `company_first_onboarding_date` | 公司首次入职时间；重入职等场景口径待确认。 |
