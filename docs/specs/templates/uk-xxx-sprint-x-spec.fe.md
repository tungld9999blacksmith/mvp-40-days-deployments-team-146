# Frontend Technical Specification

> Template sử dụng cho từng Screen / Feature của Frontend.
> Khuyến nghị mỗi Screen hoặc Feature có một file Markdown riêng trong thư mục `docs/frontend/`.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `[Feature name]` |
| Screen | `[Screen name]` |
| Route | `[Route / Navigation path]` |
| Version | `v1.0` |
| Author | `[Author]` |
| Status | `Draft / Review / Approved / Deprecated` |
| Related PRD | `[PRD link]` |
| Related User Flow | `[User Flow link]` |
| Related API | `[API Spec link]` |
| Last Updated | `YYYY-MM-DD` |

---

# 2. Screen Overview

## 2.1 Purpose

Mô tả mục đích của màn hình/feature và vấn đề người dùng cần giải quyết.

> **Example**
>
> Màn hình cho phép chủ xe chọn phương tiện, gói bảo dưỡng, trung tâm dịch vụ và khung giờ để tạo lịch hẹn.

## 2.2 Entry Points

Mô tả những nơi người dùng có thể đi tới màn hình này.

| Entry Point | Condition | Action |
|---|---|---|
| Maintenance Reminder | User taps `Đặt lịch ngay` | Navigate to this screen |
| Cost Estimate | User taps `Đặt lịch` | Navigate to this screen |
| AI Chat | AI returns booking action | Navigate to this screen |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| Appointment created successfully | `/appointments/{appointmentId}` |
| User taps Back | Previous screen |
| Authentication required | `/login` |

## 2.4 Preconditions

- User is authenticated.
- User has at least one linked vehicle.
- Required maintenance information is available.
- Selected workshop supports requested service.

---

# 3. UI Structure

## 3.1 Layout

```text
Create Appointment
├── Header
├── Vehicle Selector
├── Maintenance Package
├── Workshop Selector
├── Date Selector
├── Time Slot Selector
├── Note Input
├── Summary Card
└── Confirm Button
```

## 3.2 Screen Layout Notes

- Header contains screen title and back action.
- Main form uses a single-column layout on mobile.
- Confirm button remains visible at the bottom when practical.
- Form sections are displayed top-to-bottom according to the user flow.

---

# 4. Component Specification

## 4.1 Vehicle Selector

| Property | Value |
|---|---|
| Component | `VehicleSelector` |
| Type | Dropdown / Bottom Sheet |
| Required | Yes |
| Default Value | User's primary vehicle |
| Data Source | `GET /api/v1/vehicles` |
| Disabled When | Vehicle list is loading |
| Visibility | Always |

### Behavior

- On tap, open vehicle selection UI.
- Show all vehicles available to the current user.
- When a vehicle is selected, update `selectedVehicleId`.
- If no vehicle exists, show Empty State.

### Validation

```text
selectedVehicleId != null
```

### UI Error

```text
Vui lòng chọn xe.
```

---

## 4.2 Maintenance Package

| Property | Value |
|---|---|
| Component | `MaintenancePackageCard` |
| Type | Read-only Card / Selector |
| Required | Yes |
| Data Source | Previous flow / API |
| Visibility | When maintenance package is identified |

### Behavior

- Display package name.
- Display maintenance milestone.
- Display estimated cost when available.
- If package is not available, show fallback state.

---

## 4.3 Workshop Selector

| Property | Value |
|---|---|
| Component | `WorkshopSelector` |
| Type | Search + List |
| Required | Yes |
| Data Source | `GET /api/v1/workshops` |
| Visibility | Always |

### Behavior

- Allow search by workshop name/location.
- Display workshop operating status.
- Display whether workshop supports selected service.
- Selecting a workshop triggers time-slot loading.

---

## 4.4 Date Selector

| Property | Value |
|---|---|
| Component | `DatePicker` |
| Type | Calendar |
| Required | Yes |
| Default Value | First available date |
| Format | `YYYY-MM-DD` |
| Min Date | Current date |

### Constraints

- Past dates are disabled.
- Dates outside workshop availability are disabled.
- Fully booked dates may be disabled.

---

## 4.5 Time Slot Selector

| Property | Value |
|---|---|
| Component | `TimeSlotSelector` |
| Type | Grid / List |
| Required | Yes |
| Data Source | `GET /api/v1/workshops/{id}/slots` |

### States

- Loading
- Available
- Selected
- Unavailable
- Empty

### Behavior

- Selecting a time slot updates `selectedTimeSlot`.
- Unavailable slots cannot be selected.
- Refresh available slots when date changes.

---

## 4.6 Note Input

| Property | Value |
|---|---|
| Component | `TextArea` |
| Type | Multiline input |
| Required | No |
| Max Length | `500` |
| Placeholder | `Nhập ghi chú cho xưởng...` |

---

## 4.7 Confirm Button

| Property | Value |
|---|---|
| Component | `PrimaryButton` |
| Label | `Xác nhận đặt lịch` |
| Enabled When | Required fields are valid |
| Loading State | Disabled + spinner |

### Behavior

1. Validate current form.
2. If validation passes, submit request.
3. If request succeeds, navigate to appointment detail.
4. If request fails, keep user on current screen and display error.

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
Open Screen
   ↓
Load Initial Data
   ↓
Select Vehicle
   ↓
Select Workshop
   ↓
Select Date
   ↓
Load Time Slots
   ↓
Select Time Slot
   ↓
Enter Note (optional)
   ↓
Tap Confirm
   ↓
Validate Form
   ↓
Call Create Appointment API
   ↓
Success / Error
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Tap vehicle selector | Open vehicle picker | Show vehicles |
| Select vehicle | Update state | Show selected vehicle |
| Select workshop | Update state + load slots | Show available slots |
| Select date | Update state + refresh slots | Show slots for date |
| Tap time slot | Update selected slot | Highlight selected slot |
| Tap Confirm | Validate + submit | Create appointment |
| API success | Update state + navigate | Appointment detail |
| API failure | Map error + show message | Stay on current screen |

---

# 6. State Management

## 6.1 State Model

```text
ScreenState
├── vehicle
│   └── selectedVehicleId
├── maintenance
│   └── selectedPackageId
├── workshop
│   └── selectedWorkshopId
├── appointment
│   ├── selectedDate
│   └── selectedTimeSlot
├── form
│   └── note
├── request
│   ├── isLoading
│   ├── isSubmitting
│   └── error
└── result
    └── appointment
```

## 6.2 State Fields

| State | Type | Default | Description |
|---|---|---|---|
| `selectedVehicleId` | `string?` | `null` | Vehicle currently selected |
| `selectedPackageId` | `string?` | `null` | Maintenance package |
| `selectedWorkshopId` | `string?` | `null` | Workshop currently selected |
| `selectedDate` | `date?` | `null` | Appointment date |
| `selectedTimeSlot` | `string?` | `null` | Selected time slot |
| `note` | `string` | `""` | User note |
| `isLoading` | `boolean` | `true` | Initial data loading |
| `isSubmitting` | `boolean` | `false` | Create request in progress |
| `error` | `Error?` | `null` | Current screen error |
| `appointment` | `Appointment?` | `null` | Created appointment |

---

# 7. API Integration

> API contract chi tiết được quản lý trong API Specification. Frontend Spec chỉ mô tả cách frontend sử dụng API.

## 7.1 Load Vehicles

```http
GET /api/v1/vehicles
```

### Trigger

Screen initialization.

### Mapping

| Frontend State | API Response |
|---|---|
| `vehicleList` | `data.items` |
| `selectedVehicleId` | `data.items[0].id` (when primary vehicle exists) |

### Loading

`isLoading = true`

### Success

`isLoading = false`

### Failure

Map error to Empty State or Error State.

---

## 7.2 Load Time Slots

```http
GET /api/v1/workshops/{workshopId}/slots?date={date}
```

### Trigger

- Workshop changed.
- Date changed.

### Request Mapping

| Frontend State | Request |
|---|---|
| `selectedWorkshopId` | `{workshopId}` |
| `selectedDate` | `{date}` |

### Success

Update available time slots.

### Failure

Show retryable error and preserve selected workshop/date.

---

## 7.3 Create Appointment

```http
POST /api/v1/appointments
```

### Trigger

User taps `Xác nhận đặt lịch`.

### Request Mapping

```json
{
  "vehicleId": "{selectedVehicleId}",
  "workshopId": "{selectedWorkshopId}",
  "maintenancePackageId": "{selectedPackageId}",
  "appointmentTime": "{selectedTimeSlot}",
  "note": "{note}"
}
```

### Success

```text
HTTP 201
→ set appointment
→ navigate to /appointments/{appointmentId}
```

### Failure

Map API error code to corresponding UI behavior defined in Section 12.

---

# 8. Client-side Validation

## 8.1 Validation Rules

| Field | Rule | Error Message |
|---|---|---|
| Vehicle | Required | `Vui lòng chọn xe.` |
| Workshop | Required | `Vui lòng chọn trung tâm dịch vụ.` |
| Date | Required | `Vui lòng chọn ngày hẹn.` |
| Date | Must be today or future | `Ngày hẹn không hợp lệ.` |
| Time Slot | Required | `Vui lòng chọn khung giờ.` |
| Note | Max 500 chars | `Ghi chú tối đa 500 ký tự.` |

## 8.2 Validation Timing

- Validate individual field on blur when applicable.
- Validate the entire form on Confirm.
- Do not call API when client-side validation fails.

---

# 9. Loading States

## 9.1 Initial Loading

### Condition

Screen is opening and required data is being loaded.

### UI

- Show skeleton for list/card content.
- Disable actions that depend on unavailable data.

## 9.2 Time Slot Loading

### Condition

Workshop or date changes.

### UI

- Show loading indicator in time-slot section.
- Disable time-slot selection until request completes.

## 9.3 Submit Loading

### Condition

Create Appointment API is in progress.

### UI

- Set `isSubmitting = true`.
- Disable Confirm button.
- Show loading indicator.
- Prevent duplicate submission.

---

# 10. Empty States

## 10.1 No Vehicle

### Condition

`GET /api/v1/vehicles` returns an empty list.

### UI

**Title**

`Bạn chưa có xe nào được liên kết.`

**Description**

`Hãy liên kết xe trước khi đặt lịch bảo dưỡng.`

**CTA**

`Liên kết xe`

### Action

Navigate to `/vehicles/link`.

---

## 10.2 No Available Time Slot

### Condition

Selected workshop/date has no available slots.

### UI

**Title**

`Không có khung giờ phù hợp.`

**Description**

`Hãy chọn ngày hoặc trung tâm dịch vụ khác.`

**Action**

Allow user to change date/workshop.

---

# 11. Error States

## 11.1 General Error

```text
Không thể tải dữ liệu.
Vui lòng thử lại.

[Thử lại]
```

## 11.2 Error Mapping

| HTTP Status / Error Code | Frontend Behavior |
|---|---|
| `401 Unauthorized` | Redirect to Login |
| `403 Forbidden` | Show Permission Error |
| `404 VEHICLE_NOT_FOUND` | Show Vehicle Not Found + recovery action |
| `404 WORKSHOP_NOT_FOUND` | Refresh / reload workshop data |
| `409 APPOINTMENT_SLOT_UNAVAILABLE` | Refresh available slots + ask user to select another slot |
| `422` | Show field/business validation error |
| `500` | Show generic error + Retry |
| `503` | Show service unavailable + Retry |

---

# 12. Error Handling

## 12.1 Field-level Error

Use inline error message under the affected field.

Example:

```text
Khung giờ
[09:00] [09:30] [10:00]

Vui lòng chọn khung giờ.
```

## 12.2 Screen-level Error

Use when the whole screen or a major section cannot load.

## 12.3 Retry Behavior

When user taps `Thử lại`:

1. Retry only the failed request when possible.
2. Preserve already entered form values.
3. Do not reset unrelated UI state.

---

# 13. Navigation

## 13.1 Routes

| Route | Purpose |
|---|---|
| `/appointments/create` | Create appointment |
| `/appointments/{id}` | Appointment detail |
| `/vehicles/link` | Link a vehicle |
| `/login` | Authentication |

## 13.2 Navigation Rules

### Success

```text
Create Appointment
        ↓
201 Created
        ↓
Appointment Detail
```

### Authentication Required

```text
401
 ↓
Login
 ↓
Return to original destination
```

### Back Action

- Preserve selected values when returning from a nested picker where supported.
- Do not submit or modify server-side data on Back.

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| Create Appointment | User authenticated |
| Vehicle Selector | User has linked vehicles |
| Confirm Button | Required fields valid |
| Admin-only actions | User role = `ADMIN` |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| `USER` | Create and view own appointments |
| `SERVICE_ADVISOR` | Manage appointments for assigned workshop |
| `ADMIN` | Full access according to authorization policy |

> Frontend permission checks are for UX/visibility only. Backend authorization remains authoritative.

---

# 15. Responsive / Device Behavior

## Mobile

- Single-column layout.
- Bottom-aligned primary action where appropriate.
- Use full-width input controls.

## Tablet

- Allow wider form layout.
- Maintain readable content width.

## Desktop

- Use centered content container.
- Consider two-column layout for summary and form when appropriate.

---

# 16. Accessibility

- Every interactive element must have an accessible label.
- Touch targets should be large enough for reliable interaction.
- Do not use color alone to communicate validation or status.
- Focus should move to the relevant error when form submission fails.
- Support keyboard navigation for web applications.

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `appointment_screen_viewed` | Screen opened | `source`, `vehicleCount` |
| `vehicle_selected` | User selects vehicle | `vehicleId` |
| `workshop_selected` | User selects workshop | `workshopId` |
| `appointment_confirm_clicked` | User taps Confirm | `vehicleId`, `workshopId` |
| `appointment_created` | API success | `appointmentId` |
| `appointment_create_failed` | API failure | `errorCode` |

---

# 18. Acceptance Criteria

## AC-01 — Successful Appointment Creation

**Given** user is authenticated and has a valid vehicle.

**And** user selects a valid workshop, date, and available time slot.

**When** user taps `Xác nhận đặt lịch`.

**Then** frontend validates the form.

**And** frontend sends `POST /api/v1/appointments`.

**And** Confirm button enters loading state.

**And** when API returns `201 Created`, frontend navigates to appointment detail.

---

## AC-02 — Invalid Form

**Given** required fields are missing.

**When** user taps `Xác nhận đặt lịch`.

**Then** frontend does not call the API.

**And** relevant validation errors are displayed.

---

## AC-03 — Slot Conflict

**Given** the selected time slot was available when displayed.

**But** another user books the slot before submission.

**When** create appointment API returns `409 APPOINTMENT_SLOT_UNAVAILABLE`.

**Then** frontend shows a conflict message.

**And** frontend refreshes the available slots.

**And** user can select another slot without losing unrelated form data.

---

# 19. Technical Notes

## Frontend Stack

```text
Framework: [React / Next.js / Flutter / React Native / ...]
Language: [TypeScript / Dart / ...]
State Management: [Redux / Zustand / Riverpod / Bloc / ...]
Networking: [Axios / Dio / Fetch / ...]
Navigation: [React Router / GoRouter / ...]
UI Library: [Material UI / Flutter Material / ...]
Testing: [Jest / Vitest / Flutter Test / ...]
```

## Component Structure

```text
src/
└── features/
    └── appointment/
        ├── screens/
        ├── components/
        ├── hooks/
        ├── state/
        ├── services/
        └── types/
```

## Implementation Notes

- Keep API contract types synchronized with API specification.
- Prefer reusable components for repeated UI patterns.
- Avoid embedding business rules directly inside presentation components when the rule can be isolated in domain/state logic.

---

# 20. Open Questions

- [ ] Is workshop availability returned directly by API or calculated on frontend?
- [ ] Should the selected slot be revalidated immediately before submission?
- [ ] What is the expected behavior when the user session expires during form completion?
- [ ] Should analytics events be emitted for every validation error?

---

# 21. Related Documents

- PRD: `[link]`
- User Flow: `[link]`
- API Specification: `[link]`
- Design / Figma: `[link]`
- Architecture: `[link]`
- GitHub Issue: `[link]`
- GitHub Pull Request: `[link]`

---

# 22. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `YYYY-MM-DD` | `[Author]` | Initial version |

