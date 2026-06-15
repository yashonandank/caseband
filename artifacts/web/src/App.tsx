import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
} from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { CourseProvider } from "./context/CourseContext";
import { AppShell } from "./components/AppShell";
import Login from "./pages/Login";
import Register from "./pages/Register";
import CourseSelect from "./pages/CourseSelect";
import Dashboard from "./pages/Dashboard";
import Simulation from "./pages/Simulation";

function RequireAuth() {
  const { user } = useAuth();
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <CourseProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            <Route element={<RequireAuth />}>
              <Route path="/courses" element={<CourseSelect />} />
              <Route element={<AppShell />}>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/simulation" element={<Simulation />} />
              </Route>
            </Route>

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </CourseProvider>
    </AuthProvider>
  );
}
