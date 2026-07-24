"""抖音数据 API 客户端（基于 itfaba.com）"""
import re
import requests


API_BASE = "https://api.itfaba.com"
API_KEY = "DK_e5d5600ba02c4035be0f5c6953cf1336"
#API_CK = "hevc_supported=true; my_rd=2; enter_pc_once=1; xgplayer_user_id=644330950413; UIFID_TEMP=4a6f79d53a9eb34097631580ea9ea3ff3a17eaf36e45654c72ea19224fc01912025876b0eb5cad9a0ab60b886d96fc89cdbbdee024c29a013b09ea7e51f67b1622452a2de42684fe7e8ef444d26166de; fpk1=U2FsdGVkX1+PX7eEsklExjlEM9pAON6NFaNutFaAEg3Kdw3eFtQO0zTnr6ykoPRZdluXTQjmU3uO7oM30zoM9g==; fpk2=684fac3d8e595845640e507a9122bd55; volume_info=%7B%22volume%22%3A0.6%2C%22isMute%22%3Atrue%7D; UIFID=4a6f79d53a9eb34097631580ea9ea3ff3a17eaf36e45654c72ea19224fc01912025876b0eb5cad9a0ab60b886d96fc899d6cc11c1db2fce5b9cf0acff4b781499c2c89205c58bffecb3a5e316be32384846cd008efac60d75742376d6184f634d67ea43f03bc0065b51f95dfe2d191f8c8a253977160743f6725edbd0af09c3fe516db3875251c6029ac9fd1e7ffeddfc0af53af44c65bcaa61c5e0cae2ad26a; __ac_nonce=06a05e7de009184aa6dcd; __ac_signature=_02B4Z6wo00f01uIROcAAAIDD7LdaxD-25obiMT1AANKO66; s_v_web_id=verify_mp5mvtg2_hjNrGROL_F42w_4nrg_9Xht_St2CbgWwPMYy; douyin.com; device_web_cpu_core=8; device_web_memory_size=16; is_support_rtm_web_ts=1; home_can_add_dy_2_desktop=%220%22; dy_swidth=1512; dy_sheight=982; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A1512%2C%5C%22screen_height%5C%22%3A982%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A8%2C%5C%22device_memory%5C%22%3A16%2C%5C%22downlink%5C%22%3A10%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A50%7D%22; strategyABtestKey=%221778771938.254%22; passport_csrf_token=7fef29a8a96b51b9a41fbe715d89bcbc; passport_csrf_token_default=7fef29a8a96b51b9a41fbe715d89bcbc; bd_ticket_guard_client_web_domain=2; sdk_source_info=7e276470716a68645a606960273f276364697660272927676c715a6d6069756077273f276364697660272927666d776a68605a607d71606b766c6a6b5a7666776c7571273f275e58272927666a6b766a69605a696c6061273f27636469766027292762696a6764695a7364776c6467696076273f275e582729277672715a646971273f2763646976602729277f6b5a666475273f2763646976602729276d6a6e5a6b6a716c273f2763646976602729276c6b6f5a7f6367273f27636469766027292771273f2734303735313c3432323d323234272927676c715a75776a716a666a69273f2763646976602778; bit_env=At7E5Fg_QS36JN21HElDQBEbHeMayUPFBztQoe1O23bK1BBR2r7UQLKpKLNCiqZUtTIXOsKJ_icLSQHvZjRcOwjQXdc-FwT0JlZMqgdkr5dSnT9GqPnDyElgeqyxqTtfHC3NQ1jcra_F7a53fM9jLVlZRgUd_VuU2oeVjiLLD7gsy1lhQDDf7bfVMjdCDmNqH3iheM2mSON8JkjCaXTpaWRw_wFVKRZeShJyB9VgkSMGxXTnTJgMy7c20GyobVnfHaHy2qfBPtd0cpIwEbDhi3L8DZVWzaSUSNHWMpY5Y0u2efkVP3PNVUA6GRDOGQIyAyncO5pLD4N6g_YJD2SzZEhZ6CayYCSBIrfTQkOor3PDl1EhKnBgSMKd-RtPxrXD-POTvBq8IEWd9vo3yfmU-vASjM7lAS-zvohQhN5Pmd8157ZH3YUSop2jkWV6YORybXxQ56CBIkGDhUFvf8A5wRvBJsaG8A6bKhHRVBiBtp_fDGJtFwOT2cywsKzPj7BOqjhv6yc0lCU_JDieBC9j3knrZeqQud871G1F7RSbWY0%3D; gulu_source_res=eyJwX2luIjoiOGNjNTVmMWNlMjRmYWNlYjQ4OWEzNGZlMjg3OTQ4ZWJlNzUyZTIyN2RjYzkwZjBmMjdiYzU0NDM0YmY0ZGJlMSJ9; passport_auth_mix_state=w0r5m34y59u2ce8g3o9qdp2lpvz4r2eawlvbz3wg3kw7731z; passport_mfa_token=CjdrEgxWZUDsp8VG8rOBxfTLmQ2frEH93lR7OW54cAFQBv56ltndiLP9pVVeylqTUQOg2b%2BUNTPOGkoKPAAAAAAAAAAAAABQa6MVxcPrOCgVVwl1zNOa%2FE%2FRU%2FNFitVp%2FkFXSadOR5mJAXM%2FiTcxYWvyWYeNqCEBnRDKupEOGPax0WwgAiIBA9mrjAI%3D; d_ticket=f1c3200d84260dd10ec50204a084432fa7fda; passport_assist_user=CkHP5dtCPw3Q5-xHk4Kqvsixu00CzzXXveDHk3fNS2hWczo7PC33BD0pBZTSZb2jcgd5WqhRtbE6waMeSZ3iWTnvHBpKCjwAAAAAAAAAAAAAUGtpFBHHlCMR1zUOix0CffXxrXn2ro17wDTTMlJ1Oi2OkoYkuNMPVFwBgjcu07qYDJsQ0LmRDhiJr9ZUIAEiAQPxRy48; n_mh=ZWwiLrTJnxf-XNcNSGWysPEkYzLUbPEvYgYqvnV4Coc; sid_guard=f809f97fcdf76ba13a7c81114117df53%7C1778771983%7C5184000%7CMon%2C+13-Jul-2026+15%3A19%3A43+GMT; uid_tt=25062ff6d0b945a941b77f335958b6a9; uid_tt_ss=25062ff6d0b945a941b77f335958b6a9; sid_tt=f809f97fcdf76ba13a7c81114117df53; sessionid=f809f97fcdf76ba13a7c81114117df53; sessionid_ss=f809f97fcdf76ba13a7c81114117df53; session_tlb_tag=sttt%7C7%7C-An5f833a6E6fIERQRffU__________SaSb2-j4TEMuUShG7EXo1_2g0wGXC572DeKHktkIuwEc%3D; is_staff_user=false; has_biz_token=false; sid_ucp_v1=1.0.0-KDdlMGI2MjUyYWNkYzZhNTE5MzNkNTEwZjRhOWFkZWQ5ZTMyOGZlNzkKIQjQsvDMp8zzBhCP0JfQBhjvMSAMMP2ynrkGOAdA9AdIBBoCaGwiIGY4MDlmOTdmY2RmNzZiYTEzYTdjODExMTQxMTdkZjUz; ssid_ucp_v1=1.0.0-KDdlMGI2MjUyYWNkYzZhNTE5MzNkNTEwZjRhOWFkZWQ5ZTMyOGZlNzkKIQjQsvDMp8zzBhCP0JfQBhjvMSAMMP2ynrkGOAdA9AdIBBoCaGwiIGY4MDlmOTdmY2RmNzZiYTEzYTdjODExMTQxMTdkZjUz; _bd_ticket_crypt_cookie=017ae01a0544a5e1207d2f88578f1e1d; __security_mc_1_s_sdk_sign_data_key_web_protect=ec9c3c91-4be7-9f77; __security_mc_1_s_sdk_cert_key=998bcda8-446e-8749; __security_mc_1_s_sdk_crypt_sdk=07cad147-47f3-9981; __security_server_data_status=1; login_time=1778771983604; is_dash_user=1; publish_badge_show_info=%220%2C0%2C0%2C1778771983889%22; DiscoverFeedExposedAd=%7B%7D; SelfTabRedDotControl=%5B%5D; bd_ticket_guard_client_data=eyJiZC10aWNrZXQtZ3VhcmQtdmVyc2lvbiI6MiwiYmQtdGlja2V0LWd1YXJkLWl0ZXJhdGlvbi12ZXJzaW9uIjoxLCJiZC10aWNrZXQtZ3VhcmQtcmVlLXB1YmxpYy1rZXkiOiJCQ2ladkhLbUErdnlLQWd3VEJpR2JTMnR4YXdpa09oOEpmWllkRHZ1dFRxeHBaMTBsT3BEaVhMWHdEcnJKL3FKeDFPL2VteDNrallPRnFSeWJaTmxIemM9IiwiYmQtdGlja2V0LWd1YXJkLXdlYi12ZXJzaW9uIjoyfQ%3D%3D; FO"
API_CK = "hevc_supported=true; enter_pc_once=1; UIFID_TEMP=4a6f79d53a9eb34097631580ea9ea3ff3a17eaf36e45654c72ea19224fc01912025876b0eb5cad9a0ab60b886d96fc89cdbbdee024c29a013b09ea7e51f67b1622452a2de42684fe7e8ef444d26166de; fpk1=U2FsdGVkX1+PX7eEsklExjlEM9pAON6NFaNutFaAEg3Kdw3eFtQO0zTnr6ykoPRZdluXTQjmU3uO7oM30zoM9g==; fpk2=684fac3d8e595845640e507a9122bd55; volume_info=%7B%22volume%22%3A0.6%2C%22isMute%22%3Atrue%7D; UIFID=4a6f79d53a9eb34097631580ea9ea3ff3a17eaf36e45654c72ea19224fc01912025876b0eb5cad9a0ab60b886d96fc899d6cc11c1db2fce5b9cf0acff4b781499c2c89205c58bffecb3a5e316be32384846cd008efac60d75742376d6184f634d67ea43f03bc0065b51f95dfe2d191f8c8a253977160743f6725edbd0af09c3fe516db3875251c6029ac9fd1e7ffeddfc0af53af44c65bcaa61c5e0cae2ad26a; s_v_web_id=verify_mp5mvtg2_hjNrGROL_F42w_4nrg_9Xht_St2CbgWwPMYy; passport_csrf_token=7fef29a8a96b51b9a41fbe715d89bcbc; passport_csrf_token_default=7fef29a8a96b51b9a41fbe715d89bcbc; bd_ticket_guard_client_web_domain=2; is_staff_user=false; has_biz_token=false; __security_server_data_status=1; __ac_nonce=06a4f926a00d6d7cd3b62; __ac_signature=_02B4Z6wo00f016zn79AAAIDCokGM19eMX6-sx-tAAIF-ba; is_support_rtm_web_ts=1; dy_swidth=1512; dy_sheight=982; publish_badge_show_info=%220%2C0%2C0%2C1783599731765%22; my_rd=2; sdk_source_info=7e276470716a68645a606960273f276364697660272927676c715a6d6069756077273f276364697660272927666d776a68605a607d71606b766c6a6b5a7666776c7571273f275e58272927666a6b766a69605a696c6061273f27636469766027292762696a6764695a7364776c6467696076273f275e582729277672715a646971273f2763646976602729277f6b5a666475273f2763646976602729276d6a6e5a6b6a716c273f2763646976602729276c6b6f5a7f6367273f27636469766027292771273f273032353d36323c3c30363d3234272927676c715a75776a716a666a69273f2763646976602778; bit_env=-e4-xF4X4z1IPkRIxjO9rtsD5T7DAOvuhAWUI-1svUuyvzbsQJMGftW4MtKVRbgBx76xuCQuCLxKTiL9zO05n2qpt5S_YnP-3RbiYHzSIpAx98wRNnom_h63cvWMBTUzAWiLbkPZYE7BKvij0qeDE6Z2xBTboWRlD-ZDr0hZp4WV5rPwldY-AWoKvRuEkqg4BaXATUCnD8ae_SRqWqncdMiUGUrEfPxOF7-kJPDGZxTWxIRT1knSZuEYLvInBx8rtX_QAkDVLE2on3UhrFJJBfKRlsTZRF4kPjEnMjCkrg5kuvwJ7iYr4KFbYGjh9EAqfDcRmQvha9RAYRQ82cxxuOkUVr2Q0gBBXT0U3OHbNBv6tZvmlxZui2PWtn3P256xZrJ_q2ZUX3r8SR0zjnZQKL3jdaYSyk3ETSPyLXAORd1OJM89GnVbH7JjZV4Dt7Zh9hsldllb2rl4K4TPn9VWKvtEIY9RhmgnpkVOLLL1M1pkLsNzMSfU8xXmRZZii4CypTlRVlyubPEHIZkIOcXH5Peov8lFthRSLWAfxCpfr3U%3D; gulu_source_res=eyJwX2luIjoiYjVhZmZmMGZmOThlZGI4ZDE5NzNiMmI2NzlkYzAzZjE5Y2UyODI0NGJkYjZlNjJhNzU0ZjllMzQyYTNjOThmZCJ9; passport_auth_mix_state=0j3axy59lnt9qtvaoefzz6uzyantc8si; __druidClientInfo=JTdCJTIyY2xpZW50V2lkdGglMjIlM0ExMzUyJTJDJTIyY2xpZW50SGVpZ2h0JTIyJTNBNzcxJTJDJTIyd2lkdGglMjIlM0ExMzUyJTJDJTIyaGVpZ2h0JTIyJTNBNzcxJTJDJTIyZGV2aWNlUGl4ZWxSYXRpbyUyMiUzQTIlMkMlMjJ1c2VyQWdlbnQlMjIlM0ElMjJNb3ppbGxhJTJGNS4wJTIwKE1hY2ludG9zaCUzQiUyMEludGVsJTIwTWFjJTIwT1MlMjBYJTIwMTBfMTVfNyklMjBBcHBsZVdlYktpdCUyRjUzNy4zNiUyMChLSFRNTCUyQyUyMGxpa2UlMjBHZWNrbyklMjBDaHJvbWUlMkYxNDkuMC4wLjAlMjBTYWZhcmklMkY1MzcuMzYlMjIlN0Q=; douyin.com; device_web_cpu_core=8; device_web_memory_size=16; strategyABtestKey=%221783599763.257%22; download_guide=%222%2F20260709%2F0%22; passport_mfa_token=CjW06GH2ExAJ5%2FUjYg6pXzHzRn3n%2FmH8wy36Y4TM7yL0l2BgB50PFBUyvcYP3RRyz8iogUXNJhpKCjwAAAAAAAAAAAAAUKORzJ5KYGMHKqqULH6XDNouH8BuaDn7aHXL6udQcfPZT2ZJqnQ3gotzArGsTQiIRjEQ6q2WDhj2sdFsIAIiAQNnOuRM; d_ticket=7d4b85345071eef14d243b91c225e604a7fda; passport_assist_user=Cj0K_3UZwitgJVMfQ9Bcax3cOvt16_a01wRICe9Nib1Di5g_1sV2GMB13dq_h-coEXKQbt0Y-o29ICPdv9SRGkoKPAAAAAAAAAAAAABQo33NDl3lEOisnVVqLAFTcMLb3wn-tfdgGcRUnk5tb6MF9u2ZwUSzIv5RKXg4k2SvqRCarZYOGImv1lQgASIBA0HCpxQ%3D; n_mh=ZPAZLeVkIVeoz8HWRLQscXrA2uez8Lnx-bJkCYhD7NY; sid_guard=c6c9a7273dcdc061d884a74dbb0a06ca%7C1783599805%7C5183999%7CMon%2C+07-Sep-2026+12%3A23%3A24+GMT; uid_tt=154367c574dd9dee4d12f5bede4a13fa; uid_tt_ss=154367c574dd9dee4d12f5bede4a13fa; sid_tt=c6c9a7273dcdc061d884a74dbb0a06ca; sessionid=c6c9a7273dcdc061d884a74dbb0a06ca; sessionid_ss=c6c9a7273dcdc061d884a74dbb0a06ca; session_tlb_tag=sttt%7C16%7CxsmnJz3NwGHYhKdNuwoGyv_________36RIhTDH_8FZUTxJvrit7CdpKDruzvJeRRJkY57vKX1Q%3D; sid_ucp_v1=1.0.0-KDJhZDdkOTAwNmQzMDRjZmQ5MzRmMWFiMmM1ZDNlN2RiM2Q3ZGYxMDEKHwiszp-j9gIQvaW-0gYY7zEgDDC_9aHZBTgHQPQHSAQaAmxxIiBjNmM5YTcyNzNkY2RjMDYxZDg4NGE3NGRiYjBhMDZjYQ; ssid_ucp_v1=1.0.0-KDJhZDdkOTAwNmQzMDRjZmQ5MzRmMWFiMmM1ZDNlN2RiM2Q3ZGYxMDEKHwiszp-j9gIQvaW-0gYY7zEgDDC_9aHZBTgHQPQHSAQaAmxxIiBjNmM5YTcyNzNkY2RjMDYxZDg4NGE3NGRiYjBhMDZjYQ; _bd_ticket_crypt_cookie=183f86ca3b60a2758f9d794121d818e8; __security_mc_1_s_sdk_sign_data_key_web_protect=211bf1e6-44b5-9c86; __security_mc_1_s_sdk_cert_key=a79abf50-4b37-9906; __security_mc_1_s_sdk_crypt_sdk=955a32bb-4ee6-944e; login_time=1783599804999; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A1512%2C%5C%22screen_height%5C%22%3A982%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A8%2C%5C%22device_memory%5C%22%3A16%2C%5C%22downlink%5C%22%3A10%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A50%7D%22; SelfTabRedDotControl=%5B%7B%22id%22%3A%227630777554286168116%22%2C%22u%22%3A197%2C%22c%22%3A0%7D%2C%7B%22id%22%3A%227598440278625617963%22%2C%22u%22%3A17%2C%22c%22%3A0%7D%2C%7B%22id%22%3A%227472661842583390223%22%2C%22u%22%3A94%2C%22c%22%3A0%7D%2C%7B%22id%22%3A%227493897342987274277%22%2C%22u%22%3A80%2C%22c%22%3A0%7D%2C%7B%22id%22%3A%227203647889065642023%22%2C%22u%22%3A54%2C%22c%22%3A0%7D%2C%7B%22id%22%3A%227595136507078248500%22%2C%22u%22%3A19%2C%22c%22%3A0%7D%2C%7B%22id%22%3A%227611542843529627700%22%2C%22u%22%3A20%2C%22c%22%3A0%7D%2C%7B%22id%22%3A%227226606596640475139%22%2C%22u%22%3A119%2C%22c%22%3A0%7D%5D; FOLLOW_LIVE_POINT_INFO=%22MS4wLjABAAAA-uVzQIAf44Lxx3iRrz82SQHwJ1NzFk4iNoaoNpvNYTY%2F1783612800000%2F0%2F1783599806072%2F0%22; bd_ticket_guard_client_data=eyJiZC10aWNrZXQtZ3VhcmQtdmVyc2lvbiI6MiwiYmQtdGlja2V0LWd1YXJkLWl0ZXJhdGlvbi12ZXJzaW9uIjoxLCJiZC10aWNrZXQtZ3VhcmQtcmVlLXB1YmxpYy1rZXkiOiJCQ2ladkhLbUErdnlLQWd3VEJpR2JTMnR4YXdpa09oOEpmWllkRHZ1dFRxeHBaMTBsT3BEaVhMWHdEcnJKL3FKeDFPL2VteDNrallPRnFSeWJaTmxIemM9IiwiYmQtdGlja2V0LWd1YXJkLXdlYi12ZXJzaW9uIjoyfQ%3D%3D; home_can_add_dy_2_desktop=%221%22; ttwid=1%7Cbj-6JiWm0u-7jTFSvcRVInkS90WYnHQKHU8uOIB0III%7C1783599810%7Cf601ee85100c0871bd34de6f801c137e9870fa98d290b8dc9c5ae5a98de7a600; biz_trace_id=44555260; odin_tt=1fe5d572f7e9006e67588464f36643c2a283ad4fbe2fe19790a77aba52889de3c8f0d45e34fc4608080410a7abecd0d2693b17fbc86ee510ee122efc01d3dab7; bd_ticket_guard_client_data_v2=eyJyZWVfcHVibGljX2tleSI6IkJDaVp2SEttQSt2eUtBZ3dUQmlHYlMydHhhd2lrT2g4SmZaWWREdnV0VHF4cFoxMGxPcERpWExYd0RyckovcUp4MU8vZW14M2tqWU9GcVJ5YlpObEh6Yz0iLCJ0c19zaWduIjoidHMuMi5lYTk2N2M0ZWY1NWRiYTUzNjA1MzBiNzc0Nzk5ZDJiYTliYmQ2NjY2YzY0MDIzZTAwNjljODk4YjBkYWI3YjEwYzRmYmU4N2QyMzE5Y2YwNTMxODYyNGNlZGExNDkxMWNhNDA2ZGVkYmViZWRkYjJlMzBmY2U4ZDRmYTAyNTc1ZCIsInJlcV9jb250ZW50Ijoic2VjX3RzIiwicmVxX3NpZ24iOiJ5Nk1obHpjdk1leFR5bDdMUHNrT0p5SHVudU52cDhOY25rcWIvdGVvcXowPSIsInNlY190cyI6IiNiS3NyOWlzMlcwaHUzaFpaNWFTUFU0S0tmS0M3c241TzU2ZU5oMnZkV1JiSlBvdFV4eE1qNWgvL3RCMTQifQ%3D%3D; IsDouyinActive=false"

class DouyinApi:
    """抖音数据 API 客户端"""

    def __init__(self, api_base: str = None, api_key: str = None):
        self.api_base = api_base or API_BASE
        self.api_key = api_key or API_KEY
        self.api_ck = API_CK

    def search(self, keyword: str, count: int = 10,
               sort_type: int = 0, content_type: int = 1,
               publish_time: int = 1, filter_duration: str = "1-5") -> list[dict]:
        """
        搜索关键词，返回标准化素材列表。
        count > 30 时自动翻页。

        publish_time: 0不限 1一天 7七天 182半年
        filter_duration: "0-1" 一分钟以下, "1-5" 1-5分钟, "5-10000" 5分钟以上
        """
        results = []
        offset = 0
        remaining = count

        while remaining > 0:
            # API limit 只支持 10/20/30
            if remaining <= 10:
                limit = 10
            elif remaining <= 20:
                limit = 20
            else:
                limit = 30
            post_data = {
                "keywords": keyword,
                "limit": limit,
                "sort_type": str(sort_type),
                "content_type": str(content_type),
                "publish_time": str(publish_time),
                "filter_duration": filter_duration,
                "offset": offset,
                "ck": self.api_ck,
            }

            resp = requests.post(
                f"{self.api_base}/dyRank",
                params={"apiKey": self.api_key},
                data=post_data,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("result") != 1:
                raise RuntimeError(f"API 错误: {data.get('info', '未知错误')}")

            items = data.get("data", {}).get("data", [])
            if not items:
                break

            for item in items:
                aweme_info = item.get("aweme_info", {})
                if aweme_info:
                    parsed = self._parse_aweme(aweme_info)
                    if parsed:
                        results.append(parsed)

            has_more = data.get("data", {}).get("has_more", 0)
            cursor = data.get("data", {}).get("cursor", 0)

            if not has_more:
                break

            offset = cursor
            remaining -= len(items)

        return results

    def fetch_by_url(self, url: str) -> dict | None:
        """
        通过链接或 vid 获取单个视频信息。
        自动判断是纯数字 vid 还是短链接。
        """
        post_data = {}
        if url.strip().isdigit():
            post_data["id"] = url.strip()
        else:
            post_data["shorturl"] = url.strip()

        resp = requests.post(
            f"{self.api_base}/dyVideo/detail",
            params={"apiKey": self.api_key},
            data=post_data,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("result") != 1:
            raise RuntimeError(f"API 错误: {data.get('info', '未知错误')}")

        aweme_data = data.get("data", {})
        if not aweme_data:
            return None

        return self._parse_aweme(aweme_data)

    def _parse_aweme(self, aweme: dict) -> dict | None:
        """统一字段映射，返回标准化 dict"""
        aweme_id = aweme.get("aweme_id", "")
        if not aweme_id:
            return None

        desc = aweme.get("desc", "") or aweme.get("preview_title", "") or ""

        # 提取 #tag 标签
        tags = ",".join(re.findall(r"#(\S+?)(?:\s|$)", desc))

        # 视频 URL
        video = aweme.get("video", {})
        play_addr = video.get("play_addr", {})
        video_url = ""
        if play_addr.get("url_list"):
            video_url = play_addr["url_list"][0]

        # 封面 URL（优先 origin_cover）
        cover_url = ""
        origin_cover = video.get("origin_cover", {})
        if origin_cover.get("url_list"):
            cover_url = origin_cover["url_list"][0]
        elif video.get("cover", {}).get("url_list"):
            cover_url = video["cover"]["url_list"][0]

        # 作者
        author = aweme.get("author", {})
        author_name = author.get("nickname", "")

        # 统计数据
        statistics = aweme.get("statistics", {})

        # 原视频发布时间（Unix 时间戳）
        create_time = aweme.get("create_time", 0)

        return {
            "vid": aweme_id,
            "title": desc[:200],
            "description": desc,
            "tags": tags,
            "cover_url": cover_url,
            "video_url": video_url,
            "author": author_name,
            "author_uid": author.get("uid", ""),
            "create_time": create_time,
            "statistics": {
                "digg_count": statistics.get("digg_count", 0),
                "comment_count": statistics.get("comment_count", 0),
                "share_count": statistics.get("share_count", 0),
                "collect_count": statistics.get("collect_count", 0),
            },
            "raw_data": aweme,
        }
