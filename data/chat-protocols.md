# x.com/i/chat（XChat 新版私信）协议清单

> 自动提取自公开静态资源，XChat 构建 `cd6c611ad9c88aeecd741596c2456f259c5a8d6c`，x-web 构建 `0a94029241`，生成于 2026-10-20T09:31:17+08:00（SGT）。
> 全部为静态分析，没有向 X 发送任何登录态或写请求；queryId 未经真机验证。

## 怎么加载的

- `x.com/i/chat` 未登录会被重定向到 `/i/jf/onboarding/web?redirect_after_login=%2Fi%2Fchat`。用测试账号只读 GET 时，登录态页面仍是旧版 webpack 客户端（`responsive-web/client-web/main.*.js`），HTML 里只引用 main/vendor/i18n 三个脚本，chat 路由 chunk 在登录后才按需加载。
- x-web 里的 `chat-*.js`、`direct-messages-*.js` 只是壳：都转到 `xchat-embed-*.js`，它按 **Module Federation** 从公开清单 `https://chat.x.com/embed-v1.json` 加载远程包 `xchat`（exposes：overlays / route / settings / share / drawer），资源在 `https://abs.twimg.com/x-web/xchat/embed/<build>/`，**不需要登录**。
- 私信核心 `dm-core-*.js`（约 11 MB）是 Kotlin/JS（Apollo Kotlin + ktor + SQLDelight），GraphQL 走 `https://api.x.com/graphql/{operationId}/{operationName}`，不是 x-web 的 Relay。
- 监控现在会读取这个清单并抓取远程包（约 105 个 JS，不含语言包），把 Apollo op、端点、线上结构、wasm/worker 记到快照的 `api.xchat`，变化在通知里归到「私信 DM/XChat 远程包」。

## 端点（非 GraphQL）

| 类别 | 端点 | 用途 |
|---|---|---|
| 实时通道 | `wss://chat-ws.x.com/ws?token=<XChat token>` | 私信实时推送（thrift 二进制帧）；token 来自 `GenerateXChatTokenMutation`（`user_get_x_chat_auth_token`） |
| 实时通道（通话） | `wss://chat-ws.x.com/?token=…`、`https://call.x.com` | 音视频通话信令（xCalls*） |
| 加密密钥 | `https://realm-a.x.com/`、`https://realm-b.x.com/`、`https://d1muhwhmpsz4u8.cloudfront.net/` | Juicebox realm（PIN 托管私钥），配合 `juicebox-sdk_bg.wasm`，鉴权回调 `JuiceboxGetAuthToken` |
| 媒体 | `https://upload.x.com/1.1/media/upload.json` | 加密附件上传（配合 Initialize/FinalizeXChatMediaUploadMutation） |
| 媒体 | `https://ton.x.com/i/ton/data/xchat_media/{conv}/{id}` | 加密附件下载 |
| 其他 | `https://chat.x.com/connectors/oauth_callback` | Grok Bot 连接器 OAuth 回调 |

本地组件：wasm `juicebox-sdk_bg.wasm`, `sqlite3.wasm`；worker `camera-effect.worker.js`, `fs.worker.js`, `noise-suppressor.worklet.js`, `sqlite.worker.js`（本地 SQLite 存消息与密钥）。

## GraphQL（Apollo Kotlin，共 93 个）

「SDK」列：✅ SDK Android 配置里有同名 op 且 queryId 相同；⚠ 有同名 op 但 queryId 不同（Android 与 Web 的文档可能本来就不同，不一定是过期）；❌ SDK 没有。

### 会话列表 / 收件箱 / 消息请求

| op | 类型 | 根字段 | queryId | 变量 | SDK |
|---|---|---|---|---|---|
| `AcceptMessageRequestMutation` | mutation | `user_add_trust` | `4YtAUhUwROL6ejia63Lj6Q` | add_ckey, send_mce, targetUserId | ✅ |
| `ArchiveConversationMutation` | mutation | `xchat_archive_conversation` | `gej8xsEgeXQlYu4Oydkpfg` | action_signatures, conversationId | ❌ |
| `ConversationDeleteMutation` | mutation | `xchat_delete_conversation` | `YHFgPwrwwnml8gF8H1YhCA` | action_signatures, conversation_id | ❌ |
| `DeleteMessageRequestInboxMutation` | mutation | `xchat_delete_message_request_inbox` | `YnRLd7nyqZHq6ZFBwZqeqw` | action_signatures, inbox_type | ❌ |
| `DismissInboxSuggestionMutation` | mutation | `xchat_dismiss_inbox_suggestion` | `77p2PdEEb3_5YkgQCF-f3Q` | user_id | ❌ |
| `GetConversationEntryDetailsQuery` | query | `get_conversation_entry_details` | `_YOTZKk6OwEzokuU251B6g` | conversation_id | ❌ |
| `GetConversationPageQuery` | query | `get_conversation_page` | `GX9ZijkxG8AqRMQVD7hMnQ` | conversation_id, min_conversation_key_version, min_local_sequence_id, query_settings | ✅ |
| `GetConversationRecoveryDataQuery` | query | `get_conversation_recovery_data` | `HV-v6UtlcW5pBdgG9PTf0A` | include_all_group_member_user_objects, include_juicebox_tokens, include_participants_results_for_inbox_preview, include_user_public_keys, include_username_change, queries | ❌ |
| `GetInboxPageConversationDataQuery` | query | `get_inbox_page_conversation_data` | `4T3Z2Rwf_1SdOA6b-Oi5-w` | conversation_ids, include_all_group_member_user_objects, include_juicebox_tokens, include_participants_results_for_inbox_preview, include_user_public_keys, include_username_change | ⚠ `AdDBeQ6Tjybb1-_mnkVhOQ` |
| `GetInboxPageRequestQuery` | query | `get_inbox_page` | `txrXftx8RcSvw9jCjwRZWA` | continue_cursor, include_all_group_member_user_objects, include_juicebox_tokens, include_participants_results_for_inbox_preview, include_user_public_keys, include_username_change, query_settings | ⚠ `4QJlNf-8j_0rjIeNFegsMQ` |
| `GetInitialXChatPageQuery` | query | `get_initial_chat_page` | `Q4Mw0C6YcnjJac21wq-5NA` | include_all_group_member_user_objects, include_juicebox_tokens, include_participants_results_for_inbox_preview, include_user_public_keys, include_username_change, max_local_sequence_id, message_pull_version, query_settings | ⚠ `Owb5IWDR2WCjU4De29Jm_Q` |
| `GetMessageRequestsPageQuery` | query | `get_message_requests_page` | `9ZPeVUiUU2_iLiGecVDydg` | cursor, inbox_type, query_settings | ✅ |
| `GetPinnedMessagesPageQuery` | query | `get_pinned_messages_page` | `p9v0clZGBRgmAM5m-QRTsA` | conversation_id, cursor | ❌ |
| `MarkMessageRequestsSeenMutation` | mutation | `xchat_mark_message_requests_seen` | `g0Mnn1Y0LcHWhkmn0aQMnA` | seen_until_sequence_id | ✅ |
| `MuteConversationMutation` | mutation | `xchat_mute_conversation` | `9hq3baCBRMAG9JuLtb0ubg` | action_signatures, conversationIds | ❌ |
| `UnarchiveConversationMutation` | mutation | `xchat_unarchive_conversation` | `JIPT6zWrta18X6OEgl5Xhw` | action_signatures, conversationId | ❌ |
| `UnmuteConversationMutation` | mutation | `xchat_unmute_conversation` | `UCN8vZu2Mui2iDY0MSYfLA` | action_signatures, conversationIds | ❌ |

### 收发消息

| op | 类型 | 根字段 | queryId | 变量 | SDK |
|---|---|---|---|---|---|
| `AddWelcomeMessageToConversationMutation` | mutation | `add_api_welcome_message_to_conversation` | `0yz6RicGNMDjytAMmAP57w` | conversation_id | ✅ |
| `DeleteMessageMutation` | mutation | `xchat_delete_messages` | `4gsDQKEmYkOtvsSIpHXdQA` | action_signatures, conversation_id, delete_message_action, sequence_ids | ❌ |
| `EnableGrokBotInXChatMutation` | mutation | `xchat_enable_grok_bot_in_x_chat` | `vKfLILGtoVwJ0g_qOjRWIA` | - | ❌ |
| `FinanceSearchTags` | query | `finance_search_tags` | `lhy6u_S7pOFp62UGs8OiNA` | currency_code, page_size, query | ⚠ `lvFFUNrncNZCd9I5mKzv6A` |
| `GetCardPreviewOrJetfuelFromUrlQuery` | query | `card_by_card_uri` | `jWj8JuEgooIC5ihAYrgypw` | url | ✅ |
| `GetDangerousLinkDomainsQuery` | query | `get_dangerous_link_domains` | `GKD_rvdiHHg0QqGuX_rC6A` | digest | ❌ |
| `GetJetfuelAttachmentComposer` | query | `jetfuel_attachment_composer` | `oodcvPVHHWw6MUz0CtUBWw` | view | ✅ |
| `GetMessageEventsBySequenceIdQuery` | query | `get_message_events_by_sequence_id` | `WU1OOeTQbDQX8sc-HdCk8g` | sequence_ids | ✅ |
| `GetMessageEventsPageQuery` | query | `get_message_events_page` | `8ds29Y40jrxh_MZDbqWy0A` | continue_cursor, query_settings | ⚠ `TFvMfwNFybz0JNW-a7MxpQ` |
| `GetPostById` | query | `tweet_result_by_rest_id` | `SGv13vcTw22JONB4AghXrQ` | cta_display_location, include_boost_progress, include_can_pay, include_cta, include_profile_info, include_tombstone_pivot, rest_id | ⚠ `KE4RUXfPox4gwVsgDG0tLw` |
| `GifEnumerateCategoryQuery` | query | `gif_enumerate_category_slice` | `T1gmj8_FzuWUpe1Blp6Teg` | category, image_format, product | ⚠ `f51CbT1DbEBNOYvgYr24Nw` |
| `GifSearchQuery` | query | `gif_search_slice` | `h1iH8c0xP03NSWvLnVLPZQ` | image_format, product, query | ⚠ `1UIUhclXMiyrjWzCV_Y4kA` |
| `RemoveConversationTTLMutation` | mutation | `xchat_remove_conversation_message_duration` | `EqSXvxskUyw99ARuIbhYlg` | action_signatures, conversationId | ❌ |
| `ReportFrankedMessageMutation` | mutation | `xchat_report_franked_message` | `kjdPj17Sc-P3ODFA0h9Fhg` | conversation_id, franking_nonce_base64, media_attachments, media_upload_keys, message_bytes_base64, message_id, message_key_base64, original_message_id, original_message_key_base64, sender_id, sequence_id | ⚠ `Bxe96FqdAIre_Mvgr8KPeg` |
| `SendMessageCreateMutation` | mutation | `xchat_send_create_message_event` | `TWRPP7gnKwV_R8-tE-Dd3Q` | conversation_id, conversation_token, encoded_message_create_event, encoded_message_event_signature, message_id | ✅ |
| `SendMessageEventMutation` | mutation | `xchat_send_message_event` | `G7WwJGKvTBVb-BXhZNSVMw` | encoded_message_event | ✅ |
| `UpdateConversationTTLMutation` | mutation | `xchat_update_conversation_message_duration` | `Gu3kCEwNN2V-Az8NDk30Zg` | action_signatures, conversationId, ttlMsec | ❌ |
| `XChatGrokSearchPageQuery` | query | `get_grok_search_page` | `fViyRu-_mQfM3rS0ZvRxFQ` | search_response_id | ✅ |
| `XChatInvokeGrokBotMutation` | mutation | `xchat_invoke_grok_bot` | `8BpyTE6IEhY0taNKKd_MZA` | agent_id, conversation_id, messages_json, reply_to_message_id, reply_to_sequence_id | ❌ |
| `XChatListGrokBotsQuery` | query | `xchat_list_grok_bots` | `wX4Kq-f8DizXJC3_u0fnKw` | - | ❌ |
| `XChatSendGrokMessagePlaintextMutation` | mutation | `xchat_send_grok_message` | `LyfNWNROyAudWEnnx2zE1Q` | conversation_id, messages_json, reply_to_message_id, reply_to_sequence_id | ✅ |

### 已读

| op | 类型 | 根字段 | queryId | 变量 | SDK |
|---|---|---|---|---|---|
| `GetMessageReadTimestampsQuery` | query | `get_message_read_timestamps` | `AOomju6YIYHWl2XjC55-Cg` | conversation_id, sequence_id | ✅ |

### 加密密钥 / Juicebox / 设备登记

| op | 类型 | 根字段 | queryId | 变量 | SDK |
|---|---|---|---|---|---|
| `AddEncryptedConversationKeysMutation` | mutation | `xchat_add_encrypted_conversation_key` | `hEhvYw2gxbE4YlBjr6JlXA` | action_signatures, base64_encoded_key_rotation, conversation_id, conversation_key_version, conversation_participant_keys, rotated_pmk_bundle, ttl_msec | ❌ |
| `AddXChatPublicKeyMutation` | mutation | `user_add_public_key` | `3K4FppkWWmDPQgdqCn0NJw` | generate_version, public_key, version | ⚠ `CQsk6GRuWAVabyXqqEG1sA` |
| `DeleteSelfCustodyBackupMutation` | mutation | `user_delete_self_custody_backup` | `6W-iizyckkakySwpd2_5ng` | - | ✅ |
| `DeleteXChatPublicKeyMutation` | mutation | `user_delete_public_key` | `W5iiIL1MVw4vomq-zLPHUQ` | clearSigningPublicKeyOnly, version | ✅ |
| `FetchSelfCustodyBackupQuery` | query | `fetch_self_custody_backup` | `W31ToTUKEssJ8CEtwCfALQ` | - | ✅ |
| `GenerateXChatTokenMutation` | mutation | `user_get_x_chat_auth_token` | `Qh3fZRjPPtPoHYR_2sCZsA` | - | ✅ |
| `GetPublicKeysQuery` | query | `user_results_by_rest_ids` | `C-YphxeIcPLOGtFNGhkuOw` | ids, include_juicebox_tokens | ⚠ `nyLCqvDlxI4YoEBf-2ARmQ` |
| `ResetPasscodeMutation` | mutation | `xchat_reset_passcode` | `tmN0Hq8qLWhk3OEKHbpekA` | - | ✅ |
| `UpdateGroupPmkBundleMutation` | mutation | `xchat_update_group_pmk_bundle` | `XYrJuNAUo6nGbeh2XuoIew` | action_signatures, conversation_id, conversation_key_version, pmk_bundle | ❌ |
| `UpdateXChatUserRealmStateMutation` | mutation | `xchat_update_user_key_version_realm_state` | `B4iU-NL0I05KoyZzh9E2sw` | keyVersionRealmStates | ✅ |
| `XChatAcceptEnrollmentMutation` | mutation | `xchat_accept_enrollment` | `3OqnkNBoD_u-WQ3vYF3MwA` | enrolled_device_public_key, enrollment_id | ✅ |
| `XChatCompleteEnrollmentMutation` | mutation | `xchat_complete_enrollment` | `_z_jittTpDl2zvg2e_iI4w` | enrollment_id | ✅ |
| `XChatCreateEnrollmentSessionMutation` | mutation | `xchat_create_enrollment_session` | `sAkeiiKaXEGVI7X2zuADqg` | device_descriptor, public_key_hash | ✅ |
| `XChatDenyEnrollmentMutation` | mutation | `xchat_deny_enrollment` | `7WqlOYn720k4XH8f3-_8Xw` | enrollment_id | ✅ |
| `XChatGetEnrollmentSessionMutation` | mutation | `xchat_get_enrollment_session` | `KOvF0kG8ItHUyG0LRcKZWg` | enrollment_id | ✅ |
| `XChatInitiatePasscodeRetrievalMutation` | mutation | `xchat_initiate_passcode_retrieval` | `nTsYB72LJ1it6qlLt0EexQ` | token | ✅ |
| `XChatSendEnrollmentEncryptedKeysMutation` | mutation | `xchat_send_enrollment_encrypted_keys` | `nXbEKrcM_Gq5Q0fx0U3JBw` | encrypted_key_material, enrollment_id | ✅ |
| `XChatSendEnrollmentPublicKeyMutation` | mutation | `xchat_send_enrollment_public_key` | `aS0916UCJ9VUkwucQoUYow` | enrollment_id, new_device_public_key | ✅ |

### 媒体

| op | 类型 | 根字段 | queryId | 变量 | SDK |
|---|---|---|---|---|---|
| `FinalizeXChatMediaUploadMutation` | mutation | `xchat_finalize_media_upload` | `3O4jPQ2hwW9LbqCc-wFmqA` | conversation_id, is_public, media_hash_key, message_id, num_parts, resume_id, ttl_msec | ✅ |
| `InitializeXChatMediaUploadMutation` | mutation | `xchat_initialize_media_upload` | `6M543IPabOfZm7-yyIczdw` | content_type, conversation_id, is_public, message_id, total_bytes | ✅ |

### 群组

| op | 类型 | 根字段 | queryId | 变量 | SDK |
|---|---|---|---|---|---|
| `AddAsAdminMutation` | mutation | `xchat_add_group_admins` | `1RrduaHSFpenZuOQzgSZqA` | action_signatures, conversation_id, user_id | ❌ |
| `AddGroupMembersMutation` | mutation | `xchat_add_group_members` | `9P3IK7zSYT-xmxE08NFu7A` | action_signatures, base64_encoded_key_rotation, conversation_id, conversation_key_version, conversation_participant_keys, encrypted_avatar_url, encrypted_description, encrypted_title, group_invite_enable, rotated_pmk_bundle, screen_capture_blocking_enabled, ttl_msec, user_ids | ❌ |
| `CreateGroupConversationMutation` | mutation | `xchat_create_group` | `1yjFxgSgVkt7NceGgR5jWw` | action_signatures, admin_user_ids, avatar_url, base64_encoded_key_rotation, conversation_id, conversation_key_version, conversation_participant_keys, group_title, group_type, member_user_ids, ttl_msec | ❌ |
| `DisableGroupInviteMutation` | mutation | `xchat_disable_group_invite` | `GIIfeUYJ6NwVK9Deyw2Dqg` | action_signatures, conversation_id | ❌ |
| `EditGroupConversationMutation` | mutation | `xchat_edit_group` | `rmo8faqxHgM6s22FDQJETA` | action_signatures, avatar_url, base64_encoded_key_rotation, conversation_id, conversation_key_version, conversation_participant_keys, group_description, group_name, modified_fields, rotated_pmk_bundle | ❌ |
| `EnableGroupInviteMutation` | mutation | `xchat_enable_group_invite` | `WlxTMdzK_uh-miHVHXv15g` | action_signatures, affiliate_user_id, conversation_id, decrypted_avatar_url, decrypted_title, duration_msec, invite_url, validity_expiry_timestamp_msec, welcome_message | ❌ |
| `GetGroupJoinRequestsQuery` | query | `chat_by_conversation_id` | `Zj43ENK6vOfIS_iP15YvAA` | conversation_id, cursor, include_juicebox_tokens, include_user_public_keys, include_username_change | ⚠ `wwQzkiPnm-KafXczYi6wLA` |
| `GetSubscriberAssociatedGroupChatQuery` | query | `subscriber_associated_group_chat` | `6MM26XYWkVMEaI5HMB7tag` | - | ❌ |
| `GroupInviteDetailsQuery` | query | `chat_by_conversation_id` | `wubTkA5DWZXuf3ugyqStPg` | conversation_id, token | ✅ |
| `InitializeGroupConversationMutation` | mutation | `xchat_initialize_group` | `5zG9k_50ppvLTtPZbOC1NQ` | - | ✅ |
| `RejectJoinGroupMutation` | mutation | `xchat_reject_join_group` | `aI2--Jb8dSFiF-agdunnLw` | action_signatures, conversation_id, user_ids | ❌ |
| `RemoveAsAdminMutation` | mutation | `xchat_remove_group_admins` | `i3RDeN7PE4lDpu7dpPjbZw` | action_signatures, conversation_id, user_id | ❌ |
| `RemoveFromGroupMutation` | mutation | `xchat_remove_group_members` | `Lnm2b8oz4dnV8V-RtP1SYA` | action_signatures, conversation_id, group_key_rotation_data, user_ids | ❌ |
| `RequestToJoinGroupMutation` | mutation | `xchat_request_join_group` | `cV0VjzT5UDJW3cbcvALYOg` | action_signatures, conversation_id, token | ❌ |
| `UpdateGroupAdminSettingsMutation` | mutation | `xchat_update_group_admin_settings` | `CWJ7NtJ8LbvqTrsDSTCHvA` | action_signatures, addMember, blockScreenCapture, conversationId, editGroupInfo, editMessageTtl, sendMessage, startCall | ❌ |

### 用户 / 设置 / 其他

| op | 类型 | 根字段 | queryId | 变量 | SDK |
|---|---|---|---|---|---|
| `DisableScreenCaptureBlockingMutation` | mutation | `xchat_disable_screen_capture_blocking` | `qrnlxRj5zx9nYo7QKkJMSw` | action_signatures, conversationId | ❌ |
| `DisconnectExternalAppIntegrationMutation` | mutation | `xchat_disconnect_external_app_integration` | `xn_dhZFp6hS5rpGXsuYYeg` | client_application_id | ❌ |
| `DmAvPermissionsQuery` | query | `get_av_permissions` | `2JQ7geC1t21DHRCVkupHeQ` | recipient_ids | ⚠ `sZHGGwf5IwBHqrBzdEDPrA` |
| `DmBlockMutation` | mutation | `user_dm_block` | `8OFwIC6-G-KVg4LCu7V0oQ` | recipient_ids | ✅ |
| `DmSettingsQuery` | query | `dm_settings` | `jr8PVMRdhyJcEsDlNL87Vg` | - | ✅ |
| `DmUnblockMutation` | mutation | `user_dm_unblock` | `QH0Yp8icpGRoWcL_8GeZ-A` | include_juicebox_tokens, include_user_public_keys, include_username_change, recipient_ids | ⚠ `n3osFDAfkxHJks7mvmni1g` |
| `EnableScreenCaptureBlockingMutation` | mutation | `xchat_enable_screen_capture_blocking` | `8X3jRUeAYXWoQ025G0B73g` | action_signatures, conversationId | ❌ |
| `GetExternalAppIntegrationsQuery` | query | `get_external_app_integrations` | `LY8Ri737ejV-QyJD7iXxbQ` | - | ❌ |
| `GetSubscriberChatOverviewQuery` | query | `subscriber_chat_overview` | `kUakSWpa8_BNr-JPXq-qog` | conversation_id | ❌ |
| `GetUsersByIdsForXChat` | query | `get_member_results` | `6U-79eoYEaV8RDKC39k_RA` | ids, include_juicebox_tokens, include_user_public_keys, include_username_change, with_social_proof | ⚠ `WESYk3iex4jYRkXbeQgLrg` |
| `GetUsersByScreenNameForXChat` | query | `get_member_results_by_screen_name` | `F28l0PuF6bzi1pWvs-CRAg` | include_juicebox_tokens, include_user_public_keys, include_username_change, screen_names | ⚠ `T-daLvokYBc2X7aAuQqTXg` |
| `GetXChatNumberQuery` | query | `xchat_x_number` | `1AzMcWCerQKZUtYKUGoENA` | - | ❌ |
| `LogActionsMutation` | mutation | `xchat_log_actions` | `I8qHqtDBX8uZyYFJ4-GK7g` | raw_json_string | ✅ |
| `RotateXChatNumberMutation` | mutation | `xchat_rotate_x_number` | `H9kBrSkr45cUybwUM-RTuw` | - | ❌ |
| `SendSubscriberChatSignupInvitationsMutation` | mutation | `send_subscriber_chat_signup_invitations` | `AgVkm3FU2to1bRc_Cq6Pwg` | - | ❌ |
| `TypeaheadXChatQuery` | query | `search_by_raw_query` | `H-CyDhH23axG2oFVzsIfQg` | conv_id, include_group_check, include_juicebox_tokens, include_user_public_keys, include_username_change, max_count, query, surface | ⚠ `ufb9QfU-0zkudBGZ6e_h4w` |
| `UpdateDmSettingsMutation` | mutation | `xchat_update_dm_settings` | `o-vPPkcEbljw4E6iDtXG_A` | allow_dms_from, always_allow_dms_from_subscribers, av_settings, dm_receipt_settings | ✅ |
| `UpdateXChatNumberPermissionsMutation` | mutation | `xchat_update_x_number_permissions` | `ebN2h--YgzPWqzbYj9YhGw` | enabled, privilege, visibility | ❌ |
| `VerifyXChatNumberMutation` | mutation | `xchat_verify_x_number` | `mI2aVK3gKKz3fNOMsL8Ipw` | number, target_user_id | ❌ |

### x-web Relay（XChat 包内，非 Apollo）

通话：`xCallsStartCall`、`xCallsJoinCall`、`xCallsLeaveCall`、`xCallsRequestToken`、`xCallsGenerateAuthToken`、`xCallsSendCallEvent` 等 11 个；设置：`xChatDmSettingsQuery`；Grok 账号：`grokAccountJwtQuery`、`linkGrokAccountMutation`、`lookupGrokAccountsQuery`。这些已在主快照 `api.graphql` 里。

## 线上结构（thrift / Kotlin Adapter）

`SendMessageEventMutation` / `SendMessageCreateMutation` 发送的是加密并签名的 thrift 事件（base64），实时通道下发同类结构。已读不是独立的 GraphQL，而是 `MarkConversationReadEvent` 事件经 `SendMessageEventMutation` 发送。主要结构：

- 消息：`MessageCreateEvent`、`MessageEvent`、`MessageContents`、`MessageEdit`、`MessageDeleteEvent`、`MessageReactionAdd/Remove`、`MessageTypingEvent`、`MessageEventSignature`、`FrankingData`
- 已读：`MarkConversationRead(Event)`、`MarkConversationUnread(Event)`
- 密钥：`ConversationKeyChangeEvent`、`ConversationParticipantKey`、`PmkBundleUpdateEvent`、`MessageSigningKeyInfo`、`EnrollmentKeyTransferPayload`、`BinaryKeyPair`、`TreeKeyData`
- 实时指令：`PullMessagesInstruction`、`PullMessagesFinishedInstruction`、`SwitchToHybridPullInstruction`、`KeepAliveInstruction`、`DeviceEnrollmentInstruction`
- 媒体：`MediaAttachment`、`MessageAttachment`、`UrlAttachment`、`PostAttachment`
- 完整 152 个见快照 `api.xchat.wire_types`。

## 与 go-twitter-api 对照

- **Web 侧**（`internal/client/web/dm.go`）：只有旧版 REST `POST /1.1/dm/new2.json` 明文私信 + `dm_image` 上传。当前 x-web / XChat 未登录 JS 中都找不到 `/1.1/dm/new2.json`；登录态旧客户端 chunk 未抓取，无法确认它在网页端是否还在用。
- **Android 侧**（`internal/client/xclient/dm.go` + `clientprofile/android_1213.go`）：以原样转发 variables 的方式封装了约 50 个 XChat GraphQL op。和 Web XChat 对照：同 queryId 35 个，queryId 不同 17 个，SDK 缺 41 个。
- **缺口**：
  1. 没有端到端加密实现：密钥生成/登记（AddXChatPublicKey、Enrollment*）、会话密钥（AddEncryptedConversationKeys、UpdateGroupPmkBundle）、消息签名与 thrift 编码。SDK 的 `SendMessageCreateMutation` 只能透传调用方已构造好的密文。
  2. 没有 Juicebox（realm-a/realm-b/cloudfront 的 PIN 托管私钥恢复），新设备拿不到历史私钥就解不了历史消息。
  3. 没有实时通道 `wss://chat-ws.x.com/ws`，只能靠 GetMessageEventsPage/BySequenceId 轮询。
  4. 没有加密媒体下载（`ton.x.com/i/ton/data/xchat_media`）和解密。
  5. 缺会话管理类 mutation：归档/取消归档、静音/取消静音、删除会话/消息、消息 TTL、置顶消息分页、群组管理（建群、加/踢人、管理员、邀请链接、入群审批）、截屏保护、X 号码（XChatNumber）。
  6. Web 侧没有任何 XChat GraphQL 绑定（Web 配置只有 x-web Relay op）。
  7. SDK 里 `ConnectTabTimelineQuery`、`GetConnectPage`、`GetConversationKeyChangeEventsQuery`、`GrokDelete/RenameConversation*` 在当前 Web XChat 包中找不到，可能是 Android 专有或已下线。

## 拿不到的内容

- `x.com/i/chat` 未登录跳登录页；登录态页面是旧 webpack 客户端，chat 路由 chunk 需要浏览器执行后按需加载，静态 GET 只拿到 main/vendor/i18n，main 的 chunk 映射里也没有 chat/DM 相关条目。实际 XChat 都从上面公开的远程包加载，所以协议基本覆盖。
- worker（`fs.worker`、`sqlite.worker`、`camera-effect.worker` 等）已抓到；另有 5 个源码路径形式的引用（如 `assets/src/dms/sqlite.worker.js`、`assets/juicebox-sdk_bg.js`）返回 404，是开发路径残留，不影响。`juicebox-sdk_bg.wasm`、`sqlite3.wasm` 是二进制，只记录文件名，不下载分析。
- 已读回执、密钥变化、实时帧的具体字段编号只在 Kotlin thrift 编解码代码里，本报告只列结构名。
