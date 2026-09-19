from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView

from api import views


urlpatterns = [
    # auth
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", TokenBlacklistView.as_view(), name="logout"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="change_password"),
    path("auth/delete/", views.DeleteAccountView.as_view(), name="delete_account"),

    # market / coins
    path("market/", views.MarketView.as_view(), name="market"),
    path("coins/", views.CoinListView.as_view(), name="coins"),
    path("settings/", views.PublicSettingsView.as_view(), name="public_settings"),

    # wallet
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("wallet/<int:coin_id>/", views.WalletDetailView.as_view(), name="wallet_detail"),

    # investing / withdrawing
    path("invest/", views.InvestView.as_view(), name="invest"),
    path("invest/confirm/", views.InvestConfirmView.as_view(), name="invest_confirm"),
    path("withdrawals/", views.WithdrawalListView.as_view(), name="withdrawals"),
    path("withdraw/", views.WithdrawalCreateView.as_view(), name="withdraw_create"),

    # payment gateway callback (signed webhook from Binance Pay / your gate)
    path("gateway/webhook/", views.GatewayWebhookView.as_view(), name="gateway_webhook"),

    # admin panel
    path("admin/payout-windows/", views.AdminWindowsView.as_view(), name="admin_windows"),
    path("admin/payout-windows/<int:pk>/toggle/", views.AdminWindowToggleView.as_view(), name="admin_window_toggle"),
    path("admin/users/", views.AdminUsersListView.as_view(), name="admin_users"),
    path("admin/users/<int:pk>/action/", views.AdminUserActionView.as_view(), name="admin_user_action"),
    path("admin/users/<int:pk>/balance/", views.AdminBalanceAdjustView.as_view(), name="admin_user_balance"),
    path("admin/kyc/", views.AdminKycReviewListView.as_view(), name="admin_kyc_list"),
    path("admin/kyc/<int:pk>/review/", views.AdminKycReviewActionView.as_view(), name="admin_kyc_review"),
    path("admin/kyc/<int:pk>/file/<str:field>/", views.AdminKycFileView.as_view(), name="admin_kyc_file"),
    path("admin/payments/", views.AdminPaymentSettingsView.as_view(), name="admin_payments"),
    path("admin/payments/test/", views.AdminProviderTestView.as_view(), name="admin_payments_test"),
    path("admin/payments/wallets/<int:pk>/", views.AdminPaymentWalletDeleteView.as_view(), name="admin_payment_wallet_delete"),
    path("admin/orders/", views.AdminOrdersView.as_view(), name="admin_orders"),
    path("admin/orders/<int:pk>/confirm/", views.AdminOrderConfirmView.as_view(), name="admin_order_confirm"),
    path("admin/coins/", views.AdminCoinListView.as_view(), name="admin_coins"),
    path("admin/coins/<int:pk>/", views.AdminCoinDetailView.as_view(), name="admin_coin_detail"),

    # payout windows (users)
    path("payout-window/", views.PayoutWindowStatusView.as_view(), name="payout_window_status"),
    path("payout-window/claim/", views.PayoutWindowClaimView.as_view(), name="payout_window_claim"),

    # payouts (read only for users)
    path("payouts/", views.PayoutListView.as_view(), name="payouts"),

    # crypto accounts
    path("accounts/", views.CryptoAccountListCreateView.as_view(), name="crypto_accounts"),
    path("accounts/<int:pk>/", views.CryptoAccountDeleteView.as_view(), name="crypto_account_delete"),

    # kyc
    path("kyc/", views.KYCStatusView.as_view(), name="kyc_status"),
    path("kyc/submit/", views.KYCSubmitView.as_view(), name="kyc_submit"),

    # referrals
    path("referrals/", views.ReferralView.as_view(), name="referrals"),

    # notifications
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path("notifications/unread-count/", views.NotificationUnreadCountView.as_view(), name="notifications_unread"),
    path("notifications/read/", views.NotificationMarkReadView.as_view(), name="notifications_read"),

    # admin: notifications + platform settings
    path("admin/notifications/", views.AdminNotificationView.as_view(), name="admin_notifications"),
    path("admin/settings/", views.AdminPlatformSettingsView.as_view(), name="admin_settings"),
]