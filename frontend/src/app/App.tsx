import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/features/auth/context/AuthContext'
import RequireActiveUser from '@/features/auth/guards/RequireActiveUser'
import Login from '@/features/auth/pages/Login'
import OnboardingLayout from '@/features/auth/onboarding/OnboardingLayout'
import OnboardingIndex from '@/features/auth/onboarding/OnboardingIndex'
import ProfileStep from '@/features/auth/onboarding/pages/ProfileStep'
import VehicleStep from '@/features/auth/onboarding/pages/VehicleStep'
import VerifyingStep from '@/features/auth/onboarding/pages/VerifyingStep'
import SuccessStep from '@/features/auth/onboarding/pages/SuccessStep'
import FailedStep from '@/features/auth/onboarding/pages/FailedStep'
import OwnerLayout from '@/layouts/OwnerLayout'
import TechnicianLayout from '@/layouts/TechnicianLayout'
import Dashboard from '@/features/dashboard/pages/Dashboard'
import VehicleDetail from '@/features/vehicles/pages/VehicleDetail'
import ServiceHistory from '@/features/maintenance/pages/ServiceHistory'
import AIAssistant from '@/features/assistant/pages/AIAssistant'
import MaintenanceEstimate from '@/features/quotes/pages/MaintenanceEstimate'
import BookingLayout from '@/features/bookings/pages/BookingLayout'
import BookingStart from '@/features/bookings/pages/BookingStart'
import BookingWorkshops from '@/features/bookings/pages/BookingWorkshops'
import BookingSlots from '@/features/bookings/pages/BookingSlots'
import BookingConfirm from '@/features/bookings/pages/BookingConfirm'
import BookingTicket from '@/features/bookings/pages/BookingTicket'
import Notifications from '@/features/notifications/pages/Notifications'
import NotificationSettings from '@/features/notifications/pages/NotificationSettings'
import TechnicianDashboard from '@/features/dashboard/pages/TechnicianDashboard'
import PendingQuotes from '@/features/quotes/pages/PendingQuotes'
import QuoteReview from '@/features/quotes/pages/QuoteReview'
import { WorkshopAuthProvider } from '@/features/workshop-auth/context/WorkshopAuthContext'
import RequireActiveWorkshopOwner from '@/features/workshop-auth/guards/RequireActiveWorkshopOwner'
import WorkshopLogin from '@/features/workshop-auth/pages/WorkshopLogin'
import WorkshopOnboardingLayout from '@/features/workshop-auth/onboarding/WorkshopOnboardingLayout'
import WorkshopOnboardingIndex from '@/features/workshop-auth/onboarding/WorkshopOnboardingIndex'
import OwnerProfileStep from '@/features/workshop-auth/onboarding/pages/OwnerProfileStep'
import OperationsStep from '@/features/workshop-auth/onboarding/pages/OperationsStep'
import WorkshopVerifyingStep from '@/features/workshop-auth/onboarding/pages/WorkshopVerifyingStep'
import WorkshopSuccessStep from '@/features/workshop-auth/onboarding/pages/WorkshopSuccessStep'
import WorkshopFailedStep from '@/features/workshop-auth/onboarding/pages/WorkshopFailedStep'

/** Owner app: every owner route shares one AuthProvider (only mounted on owner routes). */
function OwnerRoot() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  )
}

/** Workshop Portal: separate session context, mounted only on portal routes. */
function WorkshopRoot() {
  return (
    <WorkshopAuthProvider>
      <Outlet />
    </WorkshopAuthProvider>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<OwnerRoot />}>
        <Route path="/" element={<Login />} />

        <Route path="/onboarding" element={<OnboardingLayout />}>
          <Route index element={<OnboardingIndex />} />
          <Route path="profile" element={<ProfileStep />} />
          <Route path="vehicle" element={<VehicleStep />} />
          <Route path="verifying" element={<VerifyingStep />} />
          <Route path="success" element={<SuccessStep />} />
          <Route path="failed" element={<FailedStep />} />
        </Route>

        <Route element={<RequireActiveUser />}>
          <Route element={<OwnerLayout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/vehicle" element={<VehicleDetail />} />
            <Route path="/history" element={<ServiceHistory />} />
            <Route path="/ai" element={<AIAssistant />} />
            <Route path="/ai/:conversationId" element={<AIAssistant />} />
            <Route path="/estimate" element={<MaintenanceEstimate />} />
            <Route path="/booking" element={<BookingLayout />}>
              <Route index element={<BookingStart />} />
              <Route path="workshops" element={<BookingWorkshops />} />
              <Route path="slots" element={<BookingSlots />} />
              <Route path="confirm" element={<BookingConfirm />} />
            </Route>
            <Route path="/bookings/:bookingId" element={<BookingTicket />} />
            <Route path="/booking-success" element={<Navigate to="/booking" replace />} />
            <Route path="/notifications" element={<Notifications showSettings />} />
            <Route path="/notifications/settings" element={<NotificationSettings />} />
          </Route>
        </Route>
      </Route>

      <Route element={<WorkshopRoot />}>
        <Route path="/workshop/login" element={<WorkshopLogin />} />

        <Route path="/workshop/onboarding" element={<WorkshopOnboardingLayout />}>
          <Route index element={<WorkshopOnboardingIndex />} />
          <Route path="profile" element={<OwnerProfileStep />} />
          <Route path="operations" element={<OperationsStep />} />
          <Route path="verifying" element={<WorkshopVerifyingStep />} />
          <Route path="success" element={<WorkshopSuccessStep />} />
          <Route path="failed" element={<WorkshopFailedStep />} />
        </Route>

        <Route element={<RequireActiveWorkshopOwner />}>
          <Route element={<TechnicianLayout />}>
            <Route path="/technician" element={<TechnicianDashboard />} />
            <Route path="/technician/quotes" element={<PendingQuotes />} />
            <Route path="/technician/quote-review" element={<QuoteReview />} />
            <Route path="/technician/notifications" element={<Notifications />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
