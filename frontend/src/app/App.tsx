import { Navigate, Outlet, Route, Routes, useParams, useSearchParams } from 'react-router-dom'
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
import Estimate from '@/features/estimate/pages/Estimate'
import EstimateCompare from '@/features/estimate/pages/EstimateCompare'
import MyBookings from '@/features/bookings/pages/MyBookings'
import Reschedule from '@/features/bookings/pages/Reschedule'
import BookingByCode, { QrEntry } from '@/features/bookings/pages/BookingByCode'
import FollowUp from '@/features/after-service/pages/FollowUp'
import WorkshopBoard from '@/features/workshop-board/pages/WorkshopBoard'
import CheckIn from '@/features/workshop-board/pages/CheckIn'
import Capacity from '@/features/workshop-board/pages/Capacity'
import BookingSettingsPage from '@/features/workshop-board/pages/BookingSettingsPage'
import BookingLayout from '@/features/bookings/pages/BookingLayout'
import BookingStart from '@/features/bookings/pages/BookingStart'
import BookingProposal from '@/features/bookings/pages/BookingProposal'
import BookingWorkshops from '@/features/bookings/pages/BookingWorkshops'
import BookingSlots from '@/features/bookings/pages/BookingSlots'
import BookingConfirm from '@/features/bookings/pages/BookingConfirm'
import BookingTicket from '@/features/bookings/pages/BookingTicket'
import Notifications from '@/features/notifications/pages/Notifications'
import NotificationSettings from '@/features/notifications/pages/NotificationSettings'
import TechnicianDashboard from '@/features/dashboard/pages/TechnicianDashboard'
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

function WorkshopBookingRedirect() {
  const { bookingId = '' } = useParams()
  return <Navigate to={`/technician/board/${encodeURIComponent(bookingId)}`} replace />
}

/** `/booking-success?bookingId=` (old link) ⇒ the ticket, else "Lịch của tôi" (us-053 §8). */
function BookingSuccessRedirect() {
  const bookingId = useSearchParams()[0].get('bookingId')
  return <Navigate to={bookingId ? `/bookings/${encodeURIComponent(bookingId)}` : '/bookings'} replace />
}

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
  return <AppRoutes />
}

function AppRoutes() {
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
            <Route path="/estimate" element={<Estimate />} />
            <Route path="/estimate/compare" element={<EstimateCompare />} />
            <Route path="/booking" element={<BookingLayout />}>
              <Route index element={<BookingStart />} />
              <Route path="proposal" element={<BookingProposal />} />
              <Route path="workshops" element={<BookingWorkshops />} />
              <Route path="slots" element={<BookingSlots />} />
              <Route path="confirm" element={<BookingConfirm />} />
            </Route>
            <Route path="/bookings" element={<MyBookings />} />
            <Route path="/bookings/by-code/:bookingCode" element={<BookingByCode />} />
            <Route path="/bookings/:bookingId" element={<BookingTicket />} />
            <Route path="/bookings/:bookingId/reschedule" element={<Reschedule />} />
            <Route path="/booking-success" element={<BookingSuccessRedirect />} />
            <Route path="/follow-ups/:followUpId" element={<FollowUp />} />
            <Route path="/notifications" element={<Notifications variant="owner" />} />
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
            <Route path="/technician/bookings/:bookingId" element={<WorkshopBookingRedirect />} />
            <Route path="/technician/board" element={<WorkshopBoard />} />
            <Route path="/technician/board/:bookingId" element={<WorkshopBoard />} />
            <Route path="/technician/check-in" element={<CheckIn />} />
            <Route path="/technician/capacity" element={<Capacity />} />
            <Route path="/technician/settings/booking" element={<BookingSettingsPage />} />
            <Route path="/technician/notifications" element={<Notifications variant="portal" />} />
          </Route>
        </Route>
      </Route>

      {/* Ticket QR (us-053): workshop session ⇒ check-in, otherwise the owner resolver. */}
      <Route path="/c/:bookingCode" element={<QrEntry />} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
