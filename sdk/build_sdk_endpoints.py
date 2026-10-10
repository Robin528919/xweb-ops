#!/usr/bin/env python3
"""Builds sdk/sdk_endpoints.json from data transcribed out of
github.com/Robin528919/go-twitter-api (commit 9d142e2675579864620f6ed0f5c178df91b42c92).
Sources:
  internal/clientprofile/web_chrome144.go   (web ops, queryIds, features, fieldToggles, REST paths)
  internal/client/web/{account,media,bootstrap,txid,engage,users,call}.go
  internal/clientprofile/android_1213.go    (android ops + feature blobs)  -> sdk/android_1213_graphql.txt
  internal/client/xclient/{coldstart,media,card,jot,client}.go (android REST)
Re-run after updating the transcription when the SDK changes."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
SDK_COMMIT = "9d142e2675579864620f6ed0f5c178df91b42c92"

webTimelineFeatures = {"rweb_video_screen_enabled":False,"rweb_cashtags_enabled":True,"profile_label_improvements_pcf_label_in_post_enabled":True,"responsive_web_profile_redirect_enabled":True,"rweb_tipjar_consumption_enabled":False,"verified_phone_label_enabled":False,"creator_subscriptions_tweet_preview_api_enabled":True,"responsive_web_graphql_timeline_navigation_enabled":True,"premium_content_api_read_enabled":False,"communities_web_enable_tweet_community_results_fetch":True,"c9s_tweet_anatomy_moderator_badge_enabled":True,"responsive_web_grok_analyze_button_fetch_trends_enabled":False,"responsive_web_grok_analyze_post_followups_enabled":True,"rweb_cashtags_composer_attachment_enabled":True,"responsive_web_jetfuel_frame":True,"responsive_web_grok_share_attachment_enabled":True,"responsive_web_grok_annotations_enabled":True,"articles_preview_enabled":True,"responsive_web_edit_tweet_api_enabled":True,"rweb_conversational_replies_downvote_enabled":False,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":True,"view_counts_everywhere_api_enabled":True,"longform_notetweets_consumption_enabled":True,"responsive_web_twitter_article_tweet_consumption_enabled":True,"content_disclosure_indicator_enabled":True,"content_disclosure_ai_generated_indicator_enabled":True,"responsive_web_grok_show_grok_translated_post":True,"responsive_web_grok_analysis_button_from_backend":True,"post_ctas_fetch_enabled":False,"freedom_of_speech_not_reach_fetch_enabled":True,"standardized_nudges_misinfo":True,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":True,"longform_notetweets_rich_text_read_enabled":True,"longform_notetweets_inline_media_enabled":False,"responsive_web_grok_image_annotation_enabled":True,"responsive_web_grok_imagine_annotation_enabled":True,"responsive_web_grok_community_note_auto_translation_is_enabled":True,"responsive_web_enhance_cards_enabled":False}
webUserByScreenNameFeatures = {"hidden_profile_subscriptions_enabled":True,"profile_label_improvements_pcf_label_in_post_enabled":True,"responsive_web_profile_redirect_enabled":True,"rweb_tipjar_consumption_enabled":False,"verified_phone_label_enabled":False,"subscriptions_verification_info_is_identity_verified_enabled":True,"subscriptions_verification_info_verified_since_enabled":True,"highlights_tweets_tab_ui_enabled":True,"responsive_web_twitter_article_notes_tab_enabled":True,"subscriptions_feature_can_gift_premium":True,"creator_subscriptions_tweet_preview_api_enabled":True,"responsive_web_graphql_timeline_navigation_enabled":True}

featCreatePost = {"grok_translations_community_note_auto_translation_is_enabled":True,"grok_translations_community_note_translation_is_enabled":True,"grok_translations_post_auto_translation_is_enabled":True,"immersive_video_status_linkable_timestamps":True,"reply_dislike_android_enabled":True,"subscriptions_feature_can_gift_premium":False,"x_lite_quick_promote_analytics_banner_enabled":False}
featTimeline = {"android_home_timeline_status_injections_facepile_enabled":False,"grok_translations_community_note_auto_translation_is_enabled":True,"grok_translations_community_note_translation_is_enabled":True,"grok_translations_post_auto_translation_is_enabled":True,"immersive_video_status_linkable_timestamps":True,"reply_dislike_android_enabled":True,"search_features_ios_relevance_prompt_inline_variant_enabled":False,"subscriptions_feature_can_gift_premium":False,"x_lite_quick_promote_analytics_banner_enabled":False}
featUserResult = {"profile_label_improvements_pcf_label_in_profile_enabled":True,"verified_phone_label_enabled":False,"super_follow_badge_privacy_enabled":True,"subscriptions_verification_info_enabled":True,"super_follow_user_api_enabled":True,"blue_business_profile_image_shape_enabled":True,"profile_label_improvements_pcf_label_in_post_enabled":True,"immersive_video_status_linkable_timestamps":True,"super_follow_exclusive_tweet_notifications_enabled":True}
android_feature_ops = {"CreatePost": featCreatePost, "UserResultByIdQuery": featUserResult}
for op in ["HomeTimeline","HomeTimelineLatest","UserProfileOriginalsTimelineQuery","UserProfileHighlightsTimelineQuery","GetFriendsFollowingTimeline","UserProfileRepliesTimelineQuery","UserProfileNewRepliesTimelineQuery","UserProfilePhotosTimelineQuery","UserProfileArticlesTimelineQuery","UserProfileAffiliatesTimelineQuery","UserProfileSuperFollowersTimelineQuery","ProfileUserPromotedTimelineQuery","UserProfileMediaTimelineQuery","UserProfileVideosTimelineQuery","ViewerBlockingTimeline","ViewerMutingTimeline","UserProfileFavoritesTimelineQuery","UserProfileRepostsTimelineQuery","ModeratedTweetTimelineQuery","UserWithProfileTweetsQueryV2","FavouritersTimelineQuery","ImmersiveViewerExploreMixerTimeline","ImmersiveViewerProfileMixerTimeline","NotificationDetailTimelineQuery","NotificationTimelineQuery","SearchTimelineQuery","TimelineByIdQuery","UserIncomingFriendshipsQuery"]:
    android_feature_ops[op] = featTimeline

web_graphql = {
  # name: dict(queryId, features, fieldToggles, host, method, variables, source, web_equivalent_hint)
  "UserByScreenName":     dict(queryId="Gb-d6r0vxPOADdG62OEBpQ", method="GET",  host="x.com/i/api/graphql", features=webUserByScreenNameFeatures, fieldToggles={"withAuxiliaryUserLabels":True}, variables=["screen_name"], web_equivalent_hint=["UserByScreenName"]),
  "UserTweetsAndReplies": dict(queryId="qUpkZU6eN8MbtQb7rC_pYg", method="GET",  host="x.com/i/api/graphql", features=webTimelineFeatures, fieldToggles={"withArticlePlainText":False}, variables=["userId","count","cursor","includePromotedContent","withCommunity","withVoice"], pagination="cursor-bottom-* entry value", web_equivalent_hint=["UserRepliesTimeline","UserTweets"]),
  "followUserMutation":   dict(queryId="m5VXpPA-MH4DH7epCa7hCg", method="POST", host="x.com/i/api/graphql", features={}, fieldToggles={}, variables=["targetUserId"], web_equivalent_hint=["followUserMutation"]),
  "FavoriteTweet":        dict(queryId="lI07N6Otwv1PhnEgXILM7A", method="POST", host="x.com/i/api/graphql", features={}, fieldToggles={}, variables=["tweet_id"], web_equivalent_hint=["likeButtonFavoriteMutation","intentModalFavoriteMutation"]),
  "CreateBookmark":       dict(queryId="aoDbu3RHznuiSkQ9aNM67Q", method="POST", host="x.com/i/api/graphql", features={}, fieldToggles={}, variables=["tweet_id"], web_equivalent_hint=["bookmarkButtonAddMutation"]),
  "UserByRestId":         dict(queryId="BwfFeYIM5H2lqDcLyU7c_Q", method="GET",  host="api.x.com/graphql",   features={}, fieldToggles={}, variables=["rest_id"], web_equivalent_hint=["intentFollowUserByRestIdQuery","userIdRedirectQuery"]),
  "Followers":            dict(queryId="JNyQdTISpzCkj_1fqxDvFg", method="GET",  host="x.com/i/api/graphql", features=webTimelineFeatures, fieldToggles={}, variables=["userId","count","cursor","includePromotedContent","withGrokTranslatedBio"], web_equivalent_hint=["followersQuery","userFollowersQuery","verifiedFollowersQuery"]),
  "Following":            dict(queryId="6IJiAg6zPdS6WBldTIwdrQ", method="GET",  host="x.com/i/api/graphql", features=webTimelineFeatures, fieldToggles={}, variables=["userId","count","cursor","includePromotedContent","withGrokTranslatedBio"], web_equivalent_hint=["followingQuery"]),
}
web_rest = [
  dict(method="POST", host="api.x.com",    path="/1.1/account/update_profile.json",        sdk_op="update_profile"),
  dict(method="POST", host="api.x.com",    path="/1.1/account/update_profile_image.json",  sdk_op="update_profile_image"),
  dict(method="POST", host="api.x.com",    path="/1.1/account/update_profile_banner.json", sdk_op="update_profile_banner"),
  dict(method="GET",  host="api.x.com",    path="/1.1/account/settings.json",              sdk_op="account_settings"),
  dict(method="POST", host="api.x.com",    path="/1.1/account/settings.json",              sdk_op="update_account_settings"),
  dict(method="POST", host="upload.x.com", path="/i/media/upload.json",                    sdk_op="media_init/append/finalize"),
  dict(method="GET",  host="upload.x.com", path="/i/media/upload.json",                    sdk_op="media_status"),
]
web_bootstrap = dict(
  page="https://x.com/messages",
  ondemand_regex=r'(\d+):"ondemand\.s"  ->  https://abs.twimg.com/responsive-web/client-web/ondemand.s.<hash>a.js',
  html_needs=["meta twitter-site-verification", "4x svg id=loading-x-anim-N"],
  note="x-client-transaction-id material (internal/client/web/txid.go)")

android_graphql = {}
for line in open(os.path.join(HERE, "android_1213_graphql.txt")):
    line = line.strip()
    if not line or line.startswith("#"): continue
    name, qid = line.split()
    android_graphql[name] = dict(queryId=qid, features=android_feature_ops.get(name, {}), host="api.x.com/graphql")
android_rest = [
  dict(method="POST", host="api.twitter.com", path="/1.1/guest/activate.json"),
  dict(method="POST", host="api.x.com",       path="/oauth2/token"),
  dict(method="GET",  host="api.x.com",       path="/1.1/account/settings.json"),
  dict(method="GET",  host="api.x.com",       path="/1.1/help/settings.json"),
  dict(method="GET",  host="api.x.com",       path="/2/badge_count/badge_count.json"),
  dict(method="POST", host="upload.x.com",    path="/1.1/media/upload2.json"),
  dict(method="POST", host="api.twitter.com", path="/1.1/jot/client_event"),
  dict(method="POST", host="caps.twitter.com",path="/v2/cards/create.json"),
  dict(method="POST", host="jf.x.com",        path="/onboarding"),
  dict(method="GET",  host="jf.x.com",        path="/onboarding/components/steps/remotes/one_tap_action_responder"),
  dict(method="POST", host="jf.x.com",        path="/onboarding/login/username"),
  dict(method="POST", host="jf.x.com",        path="/onboarding/login/actions/username"),
  dict(method="POST", host="jf.x.com",        path="/onboarding/2fa2/select"),
  dict(method="POST", host="jf.x.com",        path="/onboarding/2fa/totp"),
  dict(method="POST", host="jf.x.com",        path="/onboarding/actions/2fa"),
]
out = dict(
  sdk="github.com/Robin528919/go-twitter-api", commit=SDK_COMMIT,
  note="web = internal/client/web (x.com browser client, chrome144 profile). android = internal/client/xclient (TwitterAndroid 12.13) — included for completeness; android persisted queryIds are NOT expected to match web.",
  web=dict(graphql=web_graphql, rest=web_rest, bootstrap=web_bootstrap,
           user_fields_requested=["include_profile_interstitial_type","include_can_dm","include_blocking","include_blocked_by","include_followed_by","include_want_retweets","include_mute_edge","include_can_media_tag","include_ext_is_blue_verified","include_ext_verified_type","include_ext_profile_image_shape"]),
  android=dict(graphql=android_graphql, rest=android_rest),
)
json.dump(out, open(os.path.join(HERE, "sdk_endpoints.json"), "w"), indent=1, ensure_ascii=False)
print("web ops", len(web_graphql), "android ops", len(android_graphql))
